"""Human plays notes while a scripted agent moves shared-instrument parameters.

No agent notes are sent.
This is a deterministic musical demonstration, not a trained policy. Verify all
eight mapped parameters first: some instruments have sound-generating controls.
"""
import math
import numpy as np
from logicprogym.example_support import run_demo, supervise


def agent_action(step: int, control_hz: float) -> dict[str, np.ndarray]:
    """Phase-shifted relative movements for eight user-selected parameters."""
    phase = 2.0 * math.pi * step / (control_hz * 8.0)
    intensity = 0.35
    return {"shared/parameter_vector": np.asarray([
        intensity * math.sin(phase), intensity * math.cos(phase),
        0.50 * intensity * math.sin(0.5 * phase),
        -0.80 * intensity * math.cos(0.7 * phase),
        0.60 * intensity * math.sin(1.3 * phase),
        -intensity * math.sin(phase),
        0.70 * intensity * math.cos(1.5 * phase),
        -0.60 * intensity * math.sin(2.0 * phase),
    ], dtype=np.float32)}


def main(on_cleanup=None):
    run_demo(agent_action, __doc__, on_cleanup=on_cleanup)


def _worker(connection):
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(supervise(_worker))
