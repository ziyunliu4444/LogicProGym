"""Human-pitch to synthesizer-cutoff task for relative Mackie control."""

from __future__ import annotations

import numpy as np


class PitchCutoffTask:
    """Reward an estimated cutoff position that follows the human's pitch."""

    def __init__(self, movement_scale: float = 0.12) -> None:
        if not 0 < movement_scale <= 1:
            raise ValueError("movement_scale must be in (0, 1]")
        self.movement_scale = movement_scale
        self.cutoff_state = 0.0

    @staticmethod
    def human_note(observation: dict[str, np.ndarray], track_slot: int = 0) -> int | None:
        """Return the highest currently held human pitch, if any."""

        notes = observation["active_notes"][track_slot]
        active = np.flatnonzero(notes[:, 0] > 0.5)
        return None if active.size == 0 else int(active.max())

    @staticmethod
    def pitch_target(note: int) -> float:
        """Normalize MIDI pitch to the policy/cutoff range [-1, 1]."""

        if not 0 <= note <= 127:
            raise ValueError("MIDI note must be in 0..127")
        return note / 127.0 * 2.0 - 1.0

    def features(self, note: int) -> np.ndarray:
        """Expose target pitch and the estimated current cutoff position."""

        return np.asarray([self.pitch_target(note), self.cutoff_state], dtype=np.float32)

    def advance(self, relative_action: float, note: int) -> float:
        """Integrate one relative action and return pitch/cutoff alignment reward."""

        action = float(np.clip(relative_action, -1.0, 1.0))
        self.cutoff_state = float(
            np.clip(self.cutoff_state + action * self.movement_scale, -1.0, 1.0)
        )
        error = self.cutoff_state - self.pitch_target(note)
        return -(error * error)
