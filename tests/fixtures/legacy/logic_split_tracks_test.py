"""Test 2: human MIDI on Track 1; agent MIDI and Mackie control on Track 2."""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from logicprogym.adapters.logic_hybrid import LogicHybridAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv


CONFIG = PROJECT_ROOT / "configs" / "logic_split_tracks_test.yaml"
NOTES = (48, 52, 55, 60)


def agent_action(step: int, control_hz: float) -> dict[str, np.ndarray]:
    """Create one held agent note plus two gentle parameter velocities."""

    note = NOTES[(step // max(1, round(control_hz))) % len(NOTES)]
    gates = np.zeros(128, dtype=np.int8)
    gates[note] = 1
    phase = 2.0 * math.pi * step / (control_hz * 8.0)
    return {
        "agent/note_gate": gates,
        "agent/velocity": np.full(128, 0.60, dtype=np.float32),
        "agent/pitch_bend": np.asarray([0.0], dtype=np.float32),
        "agent/expression": np.asarray([0.75], dtype=np.float32),
        "agent/sustain": np.asarray([0.0], dtype=np.float32),
        "agent/parameter_vector": np.asarray(
            [0.20 * math.sin(phase), -0.20 * math.sin(phase)], dtype=np.float32
        ),
    }


def run(control_hz: float) -> None:
    """Play Track 2 through IAC while preserving and observing human Track 1."""

    config = LogicProGymConfig.from_yaml(CONFIG)
    env = LogicProEnv.from_config(LogicHybridAdapter.from_config(config.adapter), config)
    interval = 1.0 / control_hz
    step = 0
    try:
        env.reset()
        print("Test 2 running: you play Track 1; the dummy agent plays Track 2.")
        print("Agent MIDI uses Test Agent Bus and Mackie controls Track 2 knobs 1/2.")
        while True:
            started = time.monotonic()
            _observation, _reward, _terminated, _truncated, info = env.step(
                agent_action(step, control_hz)
            )
            for event in info["snapshot"].events:
                if event.track_id == "human":
                    print(f"HUMAN {event.kind} {event.values}", flush=True)
            step += 1
            time.sleep(max(0.0, interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        pass
    finally:
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-hz", type=float, default=4.0)
    args = parser.parse_args()
    if args.control_hz <= 0:
        parser.error("--control-hz must be positive")
    run(args.control_hz)


if __name__ == "__main__":
    main()
