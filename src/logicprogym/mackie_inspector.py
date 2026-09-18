"""Interactive setup console, separate from Gym steps and agent policies."""

import shlex
import time

from logicprogym.adapters.mackie import button_messages, send_all, vpot_message, instrument_header
from logicprogym.logic_setup import activate_parameter_view, mackie_adapter


HELP = '''lcd                 Show cached LCD text (not confirmed current values)
instrument          Select the configured track and recover Instrument view
left / right        Browse one Instrument page
track ALIAS         Switch to another configured track alias
vpot SLOT TICKS     CHANGE a knob: slot 1..8, signed ticks -63..63
help                Show commands
quit                Disconnect (does not restore knob positions)'''


def show_display(controller, emit=print):
    """Print both raw LCD rows without interpreting headers as knob values."""
    emit('Cached Logic LCD; freshness and parameter values are not verified:')
    for row in controller.lcd.rows:
        emit('|' + '|'.join(row[i:i + 7] for i in range(0, 56, 7)) + '|')


def run_console(component, track_id, *, read=input, emit=print, settle=time.sleep):
    """Read commands on demand; MIDI callbacks never flood the input prompt."""
    bridge = component.service.bridge
    if track_id not in bridge.pool.tracks:
        raise ValueError(f'Unknown track {track_id!r}; choose from {list(bridge.pool.tracks)}')
    # A name/value display is useful to a human even without the separate
    # Track/Page header. Do not cycle Instrument mode to demand that header.
    emit(HELP)
    emit('Opening Instrument view (brief startup wait); the prompt follows even if detection fails.')
    try:
        controller = activate_parameter_view(component, track_id)
    except RuntimeError as error:
        # Reading the LCD must remain possible when mode recognition fails.
        # Movement commands still run their own activation/identity checks.
        controller = bridge.pool.acquire(track_id)
        emit(f'Instrument detection warning: {error}')
        emit('Console remains available: use lcd to inspect feedback or instrument to retry.')
    show_display(controller, emit)
    while True:
        try:
            parts = shlex.split(read('mackie> '))
            if not parts:
                continue
            if parts == ['quit'] or parts == ['exit']:
                return
            if parts == ['help']:
                emit(HELP)
                continue
            if parts == ['lcd']:
                show_display(controller, emit)
                continue
            if len(parts) == 2 and parts[0] == 'track':
                if parts[1] not in bridge.pool.tracks:
                    raise ValueError(f'Choose a configured alias: {list(bridge.pool.tracks)}')
                candidate = activate_parameter_view(component, parts[1])
                track_id, controller = parts[1], candidate
            elif parts == ['instrument']:
                controller = activate_parameter_view(component, track_id)
            elif parts in (['left'], ['right']) or (len(parts) == 3 and parts[0] == 'vpot'):
                # Validate command arguments before sending selection messages.
                movement = None
                if parts[0] == 'vpot':
                    slot, ticks = int(parts[1]), int(parts[2])
                    if not 1 <= slot <= 8 or not -63 <= ticks <= 63:
                        raise ValueError('Use slot 1..8 and ticks -63..63')
                    movement = vpot_message(slot - 1, ticks)
                controller = activate_parameter_view(component, track_id)
                header = instrument_header(controller.lcd)
                identified = (header is not None and header.get('page') is not None
                              and header['track'] == bridge.pool.tracks[track_id].logic_track)
                if movement is not None and not identified:
                    raise ValueError('Parameter values are visible, but track/page identity is missing; '
                                     'no knob command sent. Use left/right to request a page display, then lcd.')
                if not identified:
                    emit('Browsing visible Instrument view; track/page identity is not confirmed.')
                bridge.feedback.invalidate()
                if movement is not None:
                    controller.output.send(movement)
                    emit(f'Requested slot {slot}: {ticks:+d} ticks; positions are not restored on exit.')
                else:
                    send_all(controller.output, button_messages('cursor_' + parts[0]))
                settle(0.3)
            else:
                raise ValueError('Unknown command; type help')
            show_display(controller, emit)
        except (ValueError, RuntimeError) as error:
            emit(f'Error: {error}')


def inspect_session(config, track_id):
    """Connect only Mackie endpoints; always close them on EOF or Ctrl-C."""
    from logicprogym import make
    env = make(config)
    component = None
    try:
        component = mackie_adapter(env)
        component.connect()
        print('Stop other agents/scanners first. Navigation changes Logic selection; only vpot changes knobs.')
        run_console(component, track_id)
    except (KeyboardInterrupt, EOFError):
        print('\nStopping inspector...')
    finally:
        try:
            if component is not None:
                component.close()
        finally:
            env.close()
        print('Inspector closed.')
    return 0
