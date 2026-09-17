"""Minimal deterministic agent for testing Logic MIDI input and output.

The agent is intentionally non-learning: a bass track plays a repeating bass
line while a lead track cycles through a C-major pattern. At the same time it
prints human events received from the configured MIDI keyboard. Press Ctrl-C to
stop; the environment sends MIDI all-notes-off before closing its ports.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from logicprogym.adapters.logic import LogicMidiAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv


DEFAULT_CONFIG = Path(__file__).parents[1] / "configs" / "logic_direct_test.yaml"
LEAD_PATTERN = (60, 62, 64, 65, 67, 69, 71, 72)
BASS_PATTERN = (36, 36, 43, 43, 45, 45, 43, 43)


def _set_track_action(
    action: dict[str, object], track: str, note: int, gate_open: bool, velocity: float
) -> None:
    """Populate all expressive-instrument controls for one agent track."""

    gates = np.zeros(128, dtype=np.int8)
    if gate_open:
        gates[note] = 1
    action[f"{track}/note_gate"] = gates
    action[f"{track}/velocity"] = np.full(128, velocity, dtype=np.float32)
    action[f"{track}/pitch_bend"] = np.asarray([0.0], dtype=np.float32)
    action[f"{track}/expression"] = np.asarray([0.80], dtype=np.float32)
    action[f"{track}/sustain"] = np.asarray([0.0], dtype=np.float32)


def build_action(
    env: LogicProEnv,
    bass_note: int,
    lead_note: int,
    bass_gate: bool,
    lead_gate: bool,
) -> dict[str, object]:
    """Create one complete two-track action accepted by the configured env."""

    # Start from a valid sample so future user-added controls remain populated,
    # then overwrite every current preset control deterministically.
    action = env.action_space.sample()
    _set_track_action(action, "agent_bass", bass_note, bass_gate, velocity=0.65)
    _set_track_action(action, "agent_lead", lead_note, lead_gate, velocity=0.75)
    return action


def print_human_events(info: dict[str, object]) -> None:
    """Print newly received human events without repeating observation history."""

    snapshot = info["snapshot"]
    for event in snapshot.events:
        if event.source.value == "human":
            print(
                f"HUMAN track={event.track_id} kind={event.kind} "
                f"values={event.values}"
            )


def run(config_path: Path, control_hz: float = 20.0) -> None:
    """Connect ports and run until interrupted by the user."""

    config = LogicProGymConfig.from_yaml(config_path)
    adapter = LogicMidiAdapter.from_config(config.adapter)
    missing = adapter.check_ports()
    if missing["missing_inputs"] or missing["missing_outputs"]:
        raise RuntimeError(
            "Configured MIDI ports were not found. "
            f"Missing inputs={missing['missing_inputs']}, "
            f"missing outputs={missing['missing_outputs']}"
        )

    env = LogicProEnv.from_config(adapter, config)
    period = 1.0 / control_hz
    lead_ticks_per_note = max(2, round(control_hz * 0.5))
    bass_ticks_per_note = max(2, round(control_hz * 1.0))
    release_ticks = max(1, round(control_hz * 0.1))
    tick = 0
    try:
        env.reset()
        print("Connected. Agent bass and lead are playing; use the keyboard to test input.")
        print("Press Ctrl-C to stop safely.")
        while True:
            lead_position = tick % lead_ticks_per_note
            bass_position = tick % bass_ticks_per_note
            lead_note = LEAD_PATTERN[
                (tick // lead_ticks_per_note) % len(LEAD_PATTERN)
            ]
            bass_note = BASS_PATTERN[
                (tick // bass_ticks_per_note) % len(BASS_PATTERN)
            ]
            action = build_action(
                env,
                bass_note=bass_note,
                lead_note=lead_note,
                bass_gate=bass_position < bass_ticks_per_note - release_ticks,
                lead_gate=lead_position < lead_ticks_per_note - release_ticks,
            )
            _, _, _, _, info = env.step(action)
            print_human_events(info)
            tick += 1
            time.sleep(period)
    except KeyboardInterrupt:
        print("\nStopping test agent...")
    finally:
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the Logic MIDI experiment YAML",
    )
    parser.add_argument("--control-hz", type=float, default=20.0)
    args = parser.parse_args()
    if args.control_hz <= 0:
        parser.error("--control-hz must be positive")
    run(args.config, args.control_hz)


if __name__ == "__main__":
    main()
