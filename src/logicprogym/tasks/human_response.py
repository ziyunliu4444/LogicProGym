"""A tiny human-responsive parameter task for live integration experiments."""

from __future__ import annotations

import numpy as np


class HumanResponseTask:
    """Map a held human note to a two-dimensional parameter target.

    This intentionally simple objective validates online learning across the
    complete keyboard → observation → policy → Mackie → Logic loop. It is not
    intended as a perceptual or aesthetic reward.
    """

    def __init__(self, human_track_slot: int = 0) -> None:
        if human_track_slot < 0:
            raise ValueError("human_track_slot cannot be negative")
        self.human_track_slot = human_track_slot

    def features(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        """Return normalized mean pitch and velocity for currently held notes."""

        notes = observation["active_notes"][self.human_track_slot]
        active = np.flatnonzero(notes[:, 0] > 0.5)
        if active.size == 0:
            return np.zeros(2, dtype=np.float32)
        pitch = float(active.mean()) / 127.0 * 2.0 - 1.0
        velocity = float(notes[active, 1].mean()) * 2.0 - 1.0
        return np.asarray([pitch, velocity], dtype=np.float32)

    @staticmethod
    def target(features: np.ndarray) -> np.ndarray:
        """Define the desired two-knob response for a human gesture."""

        return np.asarray(features, dtype=np.float32)

    @staticmethod
    def reward(action: np.ndarray, target: np.ndarray) -> float:
        """Reward actions close to the current pitch/velocity-derived target."""

        error = np.asarray(action, dtype=np.float32) - np.asarray(target, dtype=np.float32)
        return -float(np.mean(np.square(error)))
