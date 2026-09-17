"""Tests for the stable researcher-facing Gymnasium construction API."""

import gymnasium as gym
import pytest

import logicprogym
from logicprogym.adapters.logic_hybrid import LogicHybridAdapter
from logicprogym.adapters.logic_mackie import LogicMackieAdapter
from logicprogym.factory import adapter_from_config
from logicprogym.config import LogicProGymConfig


def test_public_make_builds_configured_logic_environment_without_connecting() -> None:
    env = logicprogym.make("tests/fixtures/configs/logic_split_tracks_test.yaml")
    assert isinstance(env.adapter, LogicHybridAdapter)
    assert "agent/note_gate" in env.action_space.spaces
    assert "agent/parameter_vector" in env.action_space.spaces


def test_gymnasium_registry_builds_the_same_environment() -> None:
    env = gym.make(
        logicprogym.ENV_ID,
        config_path="tests/fixtures/configs/logic_mackie_gym_test.yaml",
        disable_env_checker=True,
    )
    try:
        assert isinstance(env.unwrapped.adapter, LogicMackieAdapter)
        assert "track_2/parameter_vector" in env.action_space.spaces
    finally:
        # No reset means no live MIDI resources have been opened.
        env.close()


def test_placeholder_logic_adapter_explains_concrete_choices() -> None:
    config = LogicProGymConfig.from_yaml("tests/fixtures/configs/logic_basic.yaml")
    with pytest.raises(ValueError, match="logic_midi.*logic_mackie.*logic_hybrid"):
        adapter_from_config(config)
