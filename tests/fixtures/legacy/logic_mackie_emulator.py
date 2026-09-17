"""Interactively explore a Logic instrument through Mackie Control.

Configure this program's two virtual ports on a Mackie Control device in
Logic.  Select a software-instrument track, type ``instrument``, and Logic's
two-row Mackie display will be reconstructed in the terminal.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from contextlib import ExitStack
from pathlib import Path

import mido
import yaml

# Make the example runnable from a source checkout before the package is installed.
PROJECT_SRC = Path(__file__).parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from logicprogym.adapters.mackie import (
    MackieLcd,
    button_messages,
    send_all,
    track_select_messages,
    instrument_page,
    vpot_message,
)


TO_LOGIC = "LogicProGym Control To Logic"
FROM_LOGIC = "LogicProGym Control From Logic"
DEFAULT_STATE_FILE = Path("configs") / "logic_mackie_assignments.yaml"
DEFAULT_CATALOG_FILE = Path("configs") / "logic_mackie_catalog.yaml"

HELP = """Commands:
  use N               direct following commands to Mackie controller N
  track N             select track N (1-8 in the current bank) and inspect it
  instrument          enter Instrument Edit view
  press BUTTON        send one Mackie button press (for example, instrument)
  name                toggle names/values and print the resulting display
  left | right        change parameter page and print its eight knob names
  vpot N STEPS        turn V-Pot N (1-8) and print the resulting knob value
  lcd                 print the current reconstructed display
  live on | off       enable or disable automatic display printing
  scan [LIMIT]        discover instrument parameter pages and save YAML
  help                show these commands
  quit                close the virtual ports
"""

# Logic needs a moment to process the assignment button before a parameter
# message. This small interactive delay avoids a V-Pot turn being interpreted
# using the previous assignment (commonly Pan).
MODE_SETTLE_SECONDS = 0.10
INSTRUMENT_BUTTON_PRESSES = 2
DISPLAY_COALESCE_SECONDS = 0.025


def endpoint_names(base: str, count: int) -> list[str]:
    """Create stable, readable endpoint names for one or more controllers."""

    if count < 1:
        raise ValueError("Controller count must be at least 1")
    if count == 1:
        return [base]
    for suffix in (" To Logic", " From Logic"):
        if base.endswith(suffix):
            stem = base[: -len(suffix)]
            return [f"{stem} {index}{suffix}" for index in range(1, count + 1)]
    return [f"{base} {index}" for index in range(1, count + 1)]


def is_instrument_edit(lcd: MackieLcd) -> bool:
    """Recognize Logic's per-track Instrument Edit header."""

    return lcd.rows[0].lstrip().lower().startswith("track ") and instrument_page(lcd) is not None


def load_target_tracks(path: Path, controllers: int) -> list[int | None]:
    """Load zero-based Mackie track slots, tolerating absent older state."""

    targets: list[int | None] = [None] * controllers
    if not path.exists():
        return targets
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Mackie configuration must be a YAML mapping: {path}")
    # Prefer the descriptive user-authored format. The compact legacy list is
    # still accepted so existing experiment files continue to load.
    configured = data.get("controllers")
    if isinstance(configured, list):
        saved: list[int | None] = [None] * controllers
        for entry in configured:
            if not isinstance(entry, dict):
                continue
            controller = int(entry.get("controller", 0))
            track = entry.get("track")
            if 1 <= controller <= controllers and track is not None:
                saved[controller - 1] = int(track)
    else:
        saved = data.get("target_tracks", [])
    for index, track in enumerate(saved[:controllers]):
        if track is None:
            continue
        track = int(track)
        if 1 <= track <= 8:
            targets[index] = track - 1
    return targets


def load_controller_count(path: Path) -> int | None:
    """Read an optional controller count from a user-authored YAML profile."""

    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or "controller_count" not in data:
        return None
    count = int(data["controller_count"])
    if count < 1:
        raise ValueError("controller_count must be at least 1")
    return count


def save_target_tracks(path: Path, targets: list[int | None]) -> None:
    """Persist controller assignments as user-facing one-based track slots."""

    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "controller_count": len(targets),
        "controllers": [
            {
                "controller": index,
                "id": f"track_{target + 1}" if target is not None else f"controller_{index}",
                "track": None if target is None else target + 1,
            }
            for index, target in enumerate(targets, start=1)
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def run(
    to_logic_name: str,
    from_logic_name: str,
    show_raw: bool = False,
    controllers: int = 1,
    state_file: Path = DEFAULT_STATE_FILE,
    catalog_file: Path = DEFAULT_CATALOG_FILE,
    show_live: bool = False,
) -> None:
    """Create one or more virtual controllers and run the command prompt."""

    stopped = threading.Event()
    lcds = [MackieLcd() for _ in range(controllers)]
    outputs: list[mido.ports.BaseOutput] = []
    target_tracks = load_target_tracks(state_file, controllers)
    display_timers: list[threading.Timer | None] = [None] * controllers
    active = 0
    print_lock = threading.Lock()
    frame_condition = threading.Condition()
    frame_versions = [0] * controllers
    live_display = show_live

    def complete_display(controller: int) -> None:
        """Complete a coalesced LCD frame and optionally print it."""

        with print_lock:
            display_timers[controller] = None
            if live_display:
                print(f"\nLogic Mackie {controller + 1} display:")
                print(lcds[controller].format(), flush=True)
        with frame_condition:
            frame_versions[controller] += 1
            frame_condition.notify_all()

    def schedule_display(controller: int) -> None:
        """Debounce partial LCD packets into a single terminal refresh."""

        previous = display_timers[controller]
        if previous is not None:
            previous.cancel()
        timer = threading.Timer(
            DISPLAY_COALESCE_SECONDS, complete_display, args=(controller,)
        )
        timer.daemon = True
        display_timers[controller] = timer
        timer.start()

    def receiver(controller: int):
        """Build a callback bound to one controller's independent state."""

        def receive(message: mido.Message) -> None:
            with print_lock:
                if lcds[controller].consume(message):
                    schedule_display(controller)
                elif show_raw:
                    print(
                        f"\nLogic Mackie {controller + 1} MIDI: "
                        f"{message} | hex={message.hex()}",
                        flush=True,
                    )

        return receive

    def stop(_signum=None, _frame=None) -> None:
        stopped.set()

    def activate_target(controller: int) -> None:
        """Restore one controller's track and enter Instrument Edit mode."""

        target = target_tracks[controller]
        if target is not None:
            previous = frame_versions[controller]
            send_all(outputs[controller], track_select_messages(target))
            with frame_condition:
                frame_condition.wait_for(
                    lambda: frame_versions[controller] > previous,
                    timeout=0.5,
                )
        # Logic's Instrument button cycles through related views. Observe each
        # completed LCD frame and stop instead of blindly overshooting Edit.
        for _ in range(INSTRUMENT_BUTTON_PRESSES + 2):
            if is_instrument_edit(lcds[controller]):
                return
            previous = frame_versions[controller]
            send_all(outputs[controller], button_messages("instrument"))
            with frame_condition:
                frame_condition.wait_for(
                    lambda: frame_versions[controller] > previous,
                    timeout=0.5,
                )

    def execute(line: str) -> None:
        nonlocal active, live_display

        def ensure_instrument_mode() -> None:
            """Restore this controller's track, then enter its parameter view."""

            # Logic's selected channel strip can be changed by another control
            # surface or by the user, so restore the complete address context.
            activate_target(active)

        def wait_for_frame(previous: int, timeout: float = 1.5) -> bool:
            """Wait until Logic has completed a newer LCD refresh."""

            with frame_condition:
                return frame_condition.wait_for(
                    lambda: frame_versions[active] > previous,
                    timeout=timeout,
                )

        def wait_for_page_marker(previous: int, timeout: float = 2.0) -> bool:
            """Wait for a new atomic frame that is specifically Instrument name view."""

            with frame_condition:
                return frame_condition.wait_for(
                    lambda: frame_versions[active] > previous
                    and instrument_page(lcds[active]) is not None,
                    timeout=timeout,
                )

        def print_response(previous: int, timeout: float = 1.5) -> None:
            """Wait for Logic's reply and print one stable LCD snapshot."""

            if not wait_for_frame(previous, timeout):
                print("Logic did not return a display update.")
                return
            # A Logic response often consists of several partial SysEx writes.
            # Let the short coalescing window finish before taking the snapshot.
            time.sleep(DISPLAY_COALESCE_SECONDS * 2)
            print(f"Logic Mackie {active + 1} display:")
            print(lcds[active].format())

        def save_catalog(pages: list[dict[str, object]]) -> None:
            """Merge this controller's discovered track into the YAML catalogue."""

            catalog_file.parent.mkdir(parents=True, exist_ok=True)
            if catalog_file.exists():
                data = yaml.safe_load(catalog_file.read_text(encoding="utf-8")) or {}
            else:
                data = {}
            if not isinstance(data, dict):
                data = {}
            tracks = data.setdefault("tracks", {})
            target = target_tracks[active]
            key = f"track_{target + 1}"
            tracks[key] = {
                "logic_track": target + 1,
                "mackie_controller": active + 1,
                "pages": pages,
            }
            data["version"] = 1
            catalog_file.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        def scan_pages(limit: int | None) -> None:
            """Walk Logic's Instrument pages and record their displayed names."""

            if target_tracks[active] is None:
                raise ValueError("Assign this controller with 'track N' before scanning")
            previous = frame_versions[active]
            ensure_instrument_mode()
            found_marker = wait_for_page_marker(previous)

            # The page marker is present in name view. Toggle once if the
            # controller was left showing values instead. Wait specifically
            # for the marker because Logic may emit transitional mixer frames.
            if not found_marker:
                previous = frame_versions[active]
                send_all(outputs[active], button_messages("name_value"))
                found_marker = wait_for_page_marker(previous)
            marker = instrument_page(lcds[active])
            if not found_marker or marker is None:
                upper = lcds[active].rows[0].rstrip()
                raise RuntimeError(
                    "Logic did not expose an Instrument page marker; "
                    f"last upper LCD row was {upper!r}"
                )

            discovered: list[dict[str, object]] = []
            while True:
                current, total = instrument_page(lcds[active]) or marker
                parameters = [
                    {"slot": slot, "name": name}
                    for slot, (_upper, name) in enumerate(lcds[active].strips, start=1)
                    if name
                ]
                discovered.append({"page": current, "parameters": parameters})
                print(f"Discovered page {current}/{total}: " + ", ".join(p["name"] for p in parameters))
                if current >= total or (limit is not None and len(discovered) >= limit):
                    break
                previous = frame_versions[active]
                send_all(outputs[active], button_messages("cursor_right"))
                if not wait_for_frame(previous):
                    raise RuntimeError(f"Timed out waiting for page after {current}")
            save_catalog(discovered)
            print(f"Saved {len(discovered)} page(s) to {catalog_file}.")

        words = line.strip().lower().split()
        if not words:
            return
        command = words[0]
        if command in {"quit", "q", "exit"}:
            stopped.set()
        elif command == "use" and len(words) == 2:
            requested = int(words[1]) - 1
            if not 0 <= requested < controllers:
                raise ValueError(f"Controller must be between 1 and {controllers}")
            active = requested
            print(f"Commands now target Mackie controller {active + 1}.")
        elif command in {"instrument", "inst", "i"}:
            ensure_instrument_mode()
            print(f"Logic Mackie {active + 1} display:")
            print(lcds[active].format())
        elif command == "press" and len(words) == 2:
            send_all(outputs[active], button_messages(words[1]))
        elif command == "track" and len(words) == 2:
            track = int(words[1])
            # Store a zero-based slot in this controller's current Mackie bank.
            track_select_messages(track - 1)  # Validate before changing state.
            target_tracks[active] = track - 1
            save_target_tracks(state_file, target_tracks)
            print(f"Mackie controller {active + 1} is assigned to track {track}.")
            ensure_instrument_mode()
        elif command in {"name", "value", "nv"}:
            ensure_instrument_mode()
            previous = frame_versions[active]
            send_all(outputs[active], button_messages("name_value"))
            print_response(previous)
        elif command in {"left", "right"}:
            ensure_instrument_mode()
            previous = frame_versions[active]
            send_all(outputs[active], button_messages(f"cursor_{command}"))
            print_response(previous)
        elif command == "lcd":
            print(f"Logic Mackie {active + 1} display:")
            print(lcds[active].format())
        elif command == "live" and len(words) == 2 and words[1] in {"on", "off"}:
            live_display = words[1] == "on"
            print(f"Live display printing is {words[1]}.")
        elif command == "scan" and len(words) <= 2:
            scan_pages(None if len(words) == 1 else int(words[1]))
        elif command == "vpot" and len(words) == 3:
            ensure_instrument_mode()
            previous = frame_versions[active]
            outputs[active].send(vpot_message(int(words[1]) - 1, int(words[2])))
            print_response(previous)
        elif command == "help":
            print(HELP)
        else:
            print("Unknown command. Type 'help' for examples.")

    def prompt() -> None:
        while not stopped.is_set():
            try:
                execute(input("mackie> "))
            except (EOFError, KeyboardInterrupt):
                stopped.set()
            except (RuntimeError, TypeError, ValueError) as error:
                print(f"Invalid command: {error}")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    to_names = endpoint_names(to_logic_name, controllers)
    from_names = endpoint_names(from_logic_name, controllers)

    # CoreMIDI presents each virtual output to Logic as an input and vice versa.
    with ExitStack() as stack:
        for controller, (to_name, from_name) in enumerate(zip(to_names, from_names)):
            outputs.append(stack.enter_context(mido.open_output(to_name, virtual=True)))
            stack.enter_context(
                mido.open_input(from_name, virtual=True, callback=receiver(controller))
            )
        print(f"{controllers} virtual Mackie controller(s) are running.")
        for controller, (to_name, from_name) in enumerate(zip(to_names, from_names), 1):
            print(f'  Mackie {controller} INPUT:  "{to_name}"')
            print(f'  Mackie {controller} OUTPUT: "{from_name}"')
            target = target_tracks[controller - 1]
            assignment = "unassigned" if target is None else f"track {target + 1}"
            print(f"  Mackie {controller} TARGET: {assignment}")
        print("Restoring configured track assignments in Logic...")
        for controller, target in enumerate(target_tracks):
            if target is not None:
                activate_target(controller)
        print("Use 'use N', then 'track N', to inspect tracks independently.")
        print(HELP)
        thread = threading.Thread(target=prompt, daemon=True)
        thread.start()
        stopped.wait()
        for timer in display_timers:
            if timer is not None:
                timer.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to-logic", default=TO_LOGIC)
    parser.add_argument("--from-logic", default=FROM_LOGIC)
    parser.add_argument(
        "--controllers",
        type=int,
        default=None,
        help="number of virtual Mackie pairs (overrides the YAML configuration)",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help="file used to remember controller-to-track assignments",
    )
    parser.add_argument(
        "--catalog-file",
        type=Path,
        default=DEFAULT_CATALOG_FILE,
        help="YAML file used for discovered instrument parameters",
    )
    parser.add_argument("--raw", action="store_true", help="also print non-LCD messages")
    parser.add_argument(
        "--live",
        action="store_true",
        help="continuously print reconstructed LCD updates (off by default)",
    )
    args = parser.parse_args()
    try:
        controllers = args.controllers or load_controller_count(args.state_file) or 1
        run(
            args.to_logic,
            args.from_logic,
            args.raw,
            controllers,
            args.state_file,
            args.catalog_file,
            args.live,
        )
    except Exception as error:
        parser.exit(1, f"Could not run the virtual Mackie controller: {error}\n")


if __name__ == "__main__":
    main()
