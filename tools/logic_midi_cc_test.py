"""Test an existing Logic MIDI CC assignment without entering Learn Mode."""

import argparse
import time

import mido


def test_mapping(port, channel, cc, values, interval):
    """Send absolute requests; actual plugin values must be checked in Logic."""
    for value in values:
        port.send(mido.Message('control_change', channel=channel - 1,
                               control=cc, value=value))
        print(f'SENT channel={channel} CC={cc} value={value}', flush=True)
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='Exact output name from logicprogym devices')
    parser.add_argument('--channel', type=int, choices=range(1, 17), default=1)
    parser.add_argument('--cc', type=int, choices=range(120), default=20)
    parser.add_argument('--values', type=int, nargs='+', choices=range(128),
                        default=[32, 64, 96, 64, 64])
    parser.add_argument('--interval', type=float, default=2.0,
                        help='Seconds between requests (default: 2)')
    args = parser.parse_args()
    if not 0 < args.interval <= 60:
        parser.error('--interval must be greater than 0 and at most 60 seconds')
    try:
        available = mido.get_output_names()
        if args.port not in available:
            parser.exit(1, f'Output {args.port!r} not found. Available: {available}\n')
        print('Keep Logic Learn Mode OFF. Watch the knob you previously mapped.', flush=True)
        print(f'Testing {args.port!r}: channel={args.channel}, CC={args.cc}', flush=True)
        print('Starting in 3 seconds. Ctrl-C stops the test.', flush=True)
        time.sleep(3)
        with mido.open_output(args.port) as port:
            test_mapping(port, args.channel, args.cc, args.values, args.interval)
        print('Finished; MIDI port closed. The knob remains at the last requested setting.')
        print('Repeated identical values should hold the same position. Check this in Logic.')
    except (KeyboardInterrupt, EOFError):
        print('\nStopped; the knob remains at the last requested setting.')
    except OSError as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
