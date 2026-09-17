"""Tests for the first live human-responsive RL objective."""

import numpy as np

from logicprogym.tasks import HumanResponseTask


def test_features_encode_held_pitch_and_velocity() -> None:
    active_notes = np.zeros((2, 128, 3), dtype=np.float32)
    active_notes[0, 64] = [1.0, 0.75, 0.0]
    task = HumanResponseTask()
    features = task.features({"active_notes": active_notes})
    assert np.allclose(features, [64 / 127 * 2 - 1, 0.5])


def test_reward_is_best_at_target() -> None:
    task = HumanResponseTask()
    target = np.asarray([0.25, -0.5], dtype=np.float32)
    assert task.reward(target, target) == 0.0
    assert task.reward(np.zeros(2), target) < 0.0
