"""Send an ordinary MIDI CC sweep for Logic's user-operated Learn Assignment.

No notes, Mackie commands, or Logic preference changes are sent. A successful
send confirms MIDI delivery to the port, not the destination parameter mapping.
"""

import argparse
import time

import mido


def send_value(port, channel, cc, value):
    """Use human-facing channels 1..16 and report each requested CC value."""
    port.send(mido.Message('control_change', channel=channel - 1,
                           control=cc, value=value))
    print(f'SENT channel={channel} CC={cc} value={value}', flush=True)


def sweep(port, channel, cc):
    """Provide changing values in both directions, spaced like a physical knob."""
    for value in (0, 16, 32, 48, 64, 80, 96, 112, 127, 112, 96, 80, 64):
        send_value(port, channel, cc, value)
        time.sleep(0.25)


def run(port_name, channel, cc):
    """Keep both learning and test sends explicitly controlled by the user."""
    available = mido.get_output_names()
    if port_name not in available:
        raise ValueError(f'Output port {port_name!r} not found. Available: {available}')
    print(f'Output: {port_name!r}; channel {channel}; CC {cc}')
    print('Stop other agent scripts. Use an unassigned CC and save your Logic project.')
    print('Select the intended plugin knob in Logic, then choose Learn Assignment')
    print('for that parameter. Check the destination name before continuing.')
    input('When Logic Learn Mode is ready, press Enter to send the sweep (Ctrl-C cancels): ')
    with mido.open_output(port_name) as port:
        sweep(port, channel, cc)
        print('Sweep finished. Turn Learn Mode OFF in Logic now.')
        input('After Learn Mode is OFF, press Enter to enter the test console: ')
        print('Enter a value 0..127 to send, or quit. Try 0, 64, 127, then 64 twice.')
        print('Watch the destination knob: repeated 64 should stay at the same position.')
        print('Sent values alone do not confirm a mapping or actual knob feedback.')
        while True:
            command = input('cc> ').strip().lower()
            if command in {'quit', 'exit', 'q'}:
                break
            try:
                value = int(command)
                if not 0 <= value <= 127:
                    raise ValueError
            except ValueError:
                print('Enter an integer from 0 to 127, or quit.')
                continue
            send_value(port, channel, cc, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Exact output name from logicprogym devices')
    parser.add_argument('--channel', type=int, choices=range(1, 17), default=1)
    parser.add_argument('--cc', type=int, choices=range(120), default=20,
                        help='CC 0..119; channel-mode commands 120..127 are excluded')
    parser.add_argument('--list', action='store_true', help='List output ports without sending')
    args = parser.parse_args()
    try:
        if args.list:
            for name in mido.get_output_names():
                print(name)
            return
        if not args.port:
            parser.error('--port is required unless --list is used; run logicprogym devices')
        run(args.port, args.channel, args.cc)
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. If Logic Learn Mode is still on, turn it off manually.')
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
