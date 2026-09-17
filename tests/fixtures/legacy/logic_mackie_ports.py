"""Create the two virtual CoreMIDI endpoints for LogicProGym's Logic control surface.

Keep this process running while configuring Logic. The Python output endpoint
appears to Logic as an input, and the Python input endpoint appears to Logic as
an output. Incoming messages are printed raw. For the interactive Phase 3
emulator and decoded LCD, use ``logic_mackie_emulator.py``.
"""

from __future__ import annotations

import argparse
import signal
import threading
from datetime import datetime

import mido


TO_LOGIC = "LogicProGym Control To Logic"
FROM_LOGIC = "LogicProGym Control From Logic"


def format_message(message: mido.Message) -> str:
    """Show both Mido's semantic form and exact MIDI bytes."""

    try:
        raw = message.hex()
    except (AttributeError, ValueError):
        raw = " ".join(f"{byte:02X}" for byte in message.bytes())
    return f"{message} | hex={raw}"


def run(to_logic_name: str = TO_LOGIC, from_logic_name: str = FROM_LOGIC) -> None:
    """Create virtual endpoints and print everything Logic sends back."""

    stopped = threading.Event()
    count = 0

    def receive(message: mido.Message) -> None:
        nonlocal count
        count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"{timestamp}  #{count:05d}  {format_message(message)}", flush=True)

    def stop(_signum=None, _frame=None) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    # A virtual output is a CoreMIDI source, so Logic sees it as an input port.
    with mido.open_output(to_logic_name, virtual=True) as to_logic:
        # A virtual input is a CoreMIDI destination, so Logic sees it as output.
        with mido.open_input(
            from_logic_name, virtual=True, callback=receive
        ) as from_logic:
            # Keep strong references and display names reported by the backend.
            print("Virtual Mackie-control endpoints are running:")
            print(f'  Logic control-surface INPUT  → "{to_logic.name}"')
            print(f'  Logic control-surface OUTPUT → "{from_logic.name}"')
            print()
            print("Keep this terminal open, then add Mackie Control in Logic.")
            print("Incoming Logic messages will appear below. Press Ctrl-C to stop.")
            stopped.wait()

    print(f"Closed virtual endpoints after receiving {count} message(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to-logic", default=TO_LOGIC)
    parser.add_argument("--from-logic", default=FROM_LOGIC)
    args = parser.parse_args()
    try:
        run(args.to_logic, args.from_logic)
    except Exception as error:
        parser.exit(1, f"Could not create virtual CoreMIDI endpoints: {error}\n")


if __name__ == "__main__":
    main()
