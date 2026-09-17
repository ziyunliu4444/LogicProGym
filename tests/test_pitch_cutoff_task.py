"""Tests for the piano-pitch to synthesizer-cutoff task."""

import numpy as np
import pytest

from logicprogym.tasks import PitchCutoffTask
from tests.fixtures.legacy.logic_live_rl_agent import (
    action_steps,
    cutoff_from_mackie,
    gym_action,
    transition_reward,
)


class Snapshot:
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics


def test_pitch_target_and_relative_cutoff_reward() -> None:
    task = PitchCutoffTask(movement_scale=0.5)
    assert task.pitch_target(0) == -1.0
    assert task.pitch_target(127) == 1.0
    first = task.advance(1.0, 127)
    second = task.advance(1.0, 127)
    assert second > first
    assert second == 0.0


def test_agent_note_is_one_octave_below_and_only_cutoff_moves() -> None:
    action = gym_action(note=72, cutoff_action=0.5)
    assert np.flatnonzero(action["agent/note_gate"]).tolist() == [60]
    assert action["agent/parameter_vector"].tolist() == [0.0, 0.5]


def test_live_agent_reads_actual_cutoff_percentage_from_mackie() -> None:
    strips = (("Robotic", "2.38 %"), ("Cutoff", "50.0 %")) + (("", ""),) * 6
    info = {
        "snapshot": Snapshot(
            {"mackie": {"mackie_displays": {"agent": strips}}}
        )
    }
    assert cutoff_from_mackie(info) == (50.0, "50.0 %")

    bare_value = (("", ""), ("Cutoff", "97.66")) + (("", ""),) * 6
    info["snapshot"].diagnostics["mackie"]["mackie_displays"]["agent"] = bare_value
    value, raw = cutoff_from_mackie(info)
    assert value == pytest.approx(97.66)
    assert raw == "97.66"
    assert action_steps(0.288) == 1
    assert action_steps(0.679) == 3


def test_transition_reward_prefers_movement_toward_raw_target() -> None:
    toward, improvement, cost = transition_reward(0.0, 0.78, 62.20)
    away, away_improvement, _ = transition_reward(0.78, 0.0, 62.20)
    assert improvement == pytest.approx(0.0078)
    assert cost > 0
    assert toward > away
    assert away_improvement == pytest.approx(-0.0078)
