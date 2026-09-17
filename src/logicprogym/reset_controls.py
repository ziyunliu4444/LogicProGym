"""Opt-in absolute MIDI initialization; never infer ownership or knob values."""
import math

from logicprogym.actions.compiler import compile_actions
from logicprogym.actions.specs import UpdateMode


def reset_commands(specs, settings):
    """Validate the complete plan before any device is opened."""
    if settings is None:
        return []
    if not isinstance(settings, dict) or set(settings) - {'enabled', 'controls'}:
        raise ValueError('reset_controls requires enabled and controls only')
    if not isinstance(settings.get('enabled', False), bool):
        raise ValueError('reset_controls.enabled must be boolean')
    if not settings.get('enabled', False):
        return []
    entries = settings.get('controls', [])
    if not isinstance(entries, list):
        raise ValueError('reset_controls.controls must be a list')
    by_id = {spec.id: spec for spec in specs}
    commands, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'action', 'value', 'ownership'}:
            raise ValueError('Each reset requires action, value, and ownership: agent')
        action = entry['action']
        if not isinstance(action, str) or action not in by_id or action in seen:
            raise ValueError(f'Unknown or duplicate reset action: {action!r}')
        spec = by_id[action]
        if entry['ownership'] != 'agent' or spec.metadata.get('ownership', 'agent') != 'agent':
            raise ValueError(f'{action}: only explicitly agent-owned controls can reset')
        cc = spec.target.removeprefix('midi.cc.')
        is_cc = spec.target.startswith('midi.cc.') and cc.isdigit() and 0 <= int(cc) < 120
        if not (is_cc or spec.target == 'midi.pitch_bend') or spec.update_mode != UpdateMode.ABSOLUTE:
            raise ValueError(f'{action}: resets require absolute MIDI CC 0..119 or pitch bend; no Mackie resets')
        command = compile_actions({action: entry['value']}, [spec])[0]
        value = command.values['value']
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{action}: reset must resolve to one finite numeric value')
        low = 0 if is_cc else -1
        if not low <= value <= 1:
            raise ValueError(f'{action}: MIDI reset value must be in [{low}, 1]')
        seen.add(action)
        commands.append(command)
    return commands
