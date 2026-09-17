"""Command-line entry points for setting up LogicProGym."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from logicprogym.diagnostics import Diagnostic, diagnose
from logicprogym.factory import make


def _ports() -> tuple[list[str], list[str]]:
    # Some RtMidi/CoreMIDI initialization failures abort the native process
    # instead of raising a Python exception. Isolate enumeration so the doctor
    # can always report the failure cleanly.
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,mido; print(json.dumps([mido.get_input_names(),mido.get_output_names()]))",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            "MIDI discovery is unavailable. Ensure the macOS MIDI service is "
            "available and install LogicProGym with: python -m pip install -e ."
        )
    inputs, outputs = json.loads(probe.stdout)
    return list(inputs), list(outputs)


def _print_human(results: tuple[Diagnostic, ...]) -> None:
    for result in results:
        print(f"[{result.level:4}] {result.subject}: {result.message}")
    failures = sum(result.level == "FAIL" for result in results)
    if failures:
        print(f"\nSetup is not ready: {failures} check(s) failed.")
    else:
        print("\nConfiguration is ready for a live Logic connection.")


def doctor(config: Path, as_json: bool = False, live: bool = False) -> int:
    """Run setup checks and return a shell-compatible result code."""

    try:
        inputs, outputs = _ports()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        result = Diagnostic("FAIL", "MIDI system", str(error))
        if as_json:
            print(json.dumps([result.__dict__], indent=2))
        else:
            _print_human((result,))
        return 1
    results = diagnose(config, input_ports=inputs, output_ports=outputs)
    env = None
    if live and not any(result.level == "FAIL" for result in results):
        try:
            from logicprogym.config import LogicProGymConfig
            config_data = LogicProGymConfig.from_yaml(config)
            env = make(config)
            env.reset()
            if config_data.adapter['type'] == 'logic_midi':
                results += (Diagnostic('PASS', 'MIDI ports', 'opened; routing inside Logic is not verified'),)
            else:
                results += _verify_mackie(env, config_data)
        except Exception as error:
            results += (Diagnostic("FAIL", "live Logic connection", str(error)),)
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception as error:
                    results += (Diagnostic('FAIL', 'cleanup', str(error)),)
    if as_json:
        print(json.dumps([result.__dict__ for result in results], indent=2))
    else:
        _print_human(results)
    return 1 if any(result.level == "FAIL" for result in results) else 0


def _verify_mackie(env, config_data):
    from logicprogym.logic_setup import mackie_adapter, scan_parameters, compare_catalog
    from logicprogym.control_setup import parameter_bindings
    results = []
    component = mackie_adapter(env)
    bridge = component.service.bridge
    assert bridge is not None
    for track_id, track in bridge.pool.tracks.items():
        bindings = parameter_bindings(config_data, track_id)
        if not bindings:
            continue
        pages = scan_parameters(component, track_id, pages=max(b['page'] for b in bindings))
        missing = compare_catalog(bindings, pages)
        results.append(Diagnostic(
            'FAIL' if missing else 'PASS', f'{track_id} parameters',
            '; '.join(missing) if missing else
            f'Logic track {track.logic_track}: page/slot names matched at verification time',
        ))
    return tuple(results)


def logic_scan(config: Path, track_id: str, pages: int, output: Path, start_page=None) -> int:
    """Connect to Logic, scan one instrument, and save its parameter catalog."""

    from logicprogym.logic_setup import mackie_adapter, scan_parameters, save_catalog
    env = make(config)
    try:
        env.reset()
        component = mackie_adapter(env)
        bridge = component.service.bridge
        if bridge is None or track_id not in bridge.pool.tracks:
            choices = "none" if bridge is None else ", ".join(bridge.pool.tracks)
            raise ValueError(f"Unknown Mackie track {track_id!r}; choices: {choices}")
        track = bridge.pool.tracks[track_id]
        found = scan_parameters(component, track_id, pages=pages, start_page=start_page)
        controller = bridge.pool.acquire(track_id)
        save_catalog(
            output,
            track_id=track_id,
            logic_track=track.logic_track,
            controller=controller.index + 1,
            pages=found,
        )
        for page in found:
            names = ", ".join(item["name"] for item in page["parameters"])
            print(f"Page {page['page']}: {names or '(no names returned)'}")
        print(f"Saved {len(found)} page(s) to {output}")
        return 0
    finally:
        env.close()


def devices(as_json: bool = False) -> int:
    """List exact MIDI names without opening ports or sending messages."""
    try:
        inputs, outputs = _ports()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        if as_json:
            print(json.dumps({'error': str(error)}))
        else:
            print(f'MIDI discovery failed: {error}', file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({'inputs': inputs, 'outputs': outputs}, indent=2))
    else:
        for label, names in [('MIDI inputs (human keyboard/controllers)', inputs),
                             ('MIDI outputs (agent destinations)', outputs)]:
            print(label + ':')
            for name in names:
                print(f'  {json.dumps(name)}')
            if not names:
                print('  (none found)')
        print('Copy exact names into your session YAML. No MIDI messages were sent.')
        print('Create/enable an IAC bus in Audio MIDI Setup if you need an agent destination.')
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="logicprogym")
    commands = parser.add_subparsers(dest="command", required=True)
    device_parser = commands.add_parser('devices', help='list available MIDI inputs and outputs without sending')
    device_parser.add_argument('--json', action='store_true', dest='as_json')
    doctor_parser = commands.add_parser(
        "doctor", help="check a Logic YAML configuration and MIDI setup"
    )
    doctor_parser.add_argument("config", type=Path)
    doctor_parser.add_argument("--json", action="store_true", dest="as_json")
    doctor_parser.add_argument(
        "--live", action="store_true", help="connect and validate Mackie feedback"
    )
    logic_parser = commands.add_parser("logic", help="Logic Pro setup tools")
    logic_commands = logic_parser.add_subparsers(dest="logic_command", required=True)
    scan_parser = logic_commands.add_parser("scan", help="scan Instrument parameters")
    scan_parser.add_argument("config", type=Path)
    scan_parser.add_argument("--track", required=True, dest="track_id")
    scan_parser.add_argument("--pages", type=int, default=1)
    scan_parser.add_argument("--start-page", type=int,
                             help="Explicit current page when Logic truncates the page number")
    scan_parser.add_argument(
        "--output", type=Path, default=Path("configs/logic_mackie_catalog.yaml")
    )
    preview_parser = commands.add_parser('preview', help='show enabled track controls without connecting to Logic')
    preview_parser.add_argument('config', type=Path)
    args = parser.parse_args()
    if args.command == 'devices':
        raise SystemExit(devices(args.as_json))
    if args.command == 'preview':
        from logicprogym.control_setup import preview
        print(preview(args.config))
        return
    if args.command == "doctor":
        raise SystemExit(doctor(args.config, args.as_json, args.live))
    if args.command == "logic" and args.logic_command == "scan":
        raise SystemExit(logic_scan(args.config, args.track_id, args.pages, args.output, args.start_page))


if __name__ == "__main__":
    main()
