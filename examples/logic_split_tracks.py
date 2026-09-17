"""Human plays one track while a scripted agent plays notes and moves knobs on another.

This is a deterministic
arpeggio/parameter-motion demonstration, not a learned accompaniment policy.
Use separate human/agent MIDI routes and verify the two mapped parameters.
"""
import math
import numpy as np
from logicprogym.example_support import run_demo, supervise


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



def main(on_cleanup=None):
    run_demo(agent_action, __doc__, on_cleanup=on_cleanup)


def _worker(connection):
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(supervise(_worker))
