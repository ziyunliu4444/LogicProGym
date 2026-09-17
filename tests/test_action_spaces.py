"""Tests for policy representations and DAW-neutral command compilation."""

import numpy as np
from gymnasium import spaces

from logicprogym.actions.compiler import compile_actions
from logicprogym.actions.presets import (
    continuous_pitch,
    discrete_pitch,
    discrete_velocity,
    expressive_instrument,
)
from logicprogym.actions.specs import ActionRepresentation, ActionSpec, UpdateMode
from logicprogym.spaces import build_action_space


def test_expressive_instrument_sample_is_valid():
    """Every sampled preset action must be contained by its declared space."""

    space = build_action_space(expressive_instrument("agent"))
    sample = space.sample()
    assert space.contains(sample)
    assert sample["note_gate"].shape == (128,)
    assert np.all(sample["pitch_bend"] >= -1.0)


def test_discrete_scale_pitch_maps_index_to_note():
    """A categorical policy index resolves to the configured musical pitch."""

    spec = discrete_pitch("agent", [60, 62, 64, 65, 67])
    space = build_action_space([spec])

    assert isinstance(space["pitch"], spaces.Discrete)
    command = compile_actions({"pitch": 2}, [spec])[0]
    assert command.track_id == "agent"
    assert command.kind == "musical.pitch"
    assert command.values["policy_value"] == 2
    assert command.values["value"] == 64


def test_continuous_pitch_remains_fractional_until_adapter_encoding():
    """Fractional pitch must not be quantized before reaching an adapter."""

    spec = continuous_pitch("trombone", 40.0, 72.0)
    command = compile_actions({"pitch": np.array([60.5], dtype=np.float32)}, [spec])[0]

    assert command.values["value"] == [60.5]
    assert command.values["encoding"] == {"unit": "midi_note"}


def test_velocity_can_have_a_discrete_policy_representation():
    """Researchers can intentionally restrict velocity to selected levels."""

    spec = discrete_velocity("agent", [32, 64, 96, 127])
    command = compile_actions({"velocity": 3}, [spec])[0]

    assert command.values["value"] == 127
    assert command.values["representation"] == "discrete"
    assert command.values["encoding"]["integer_range"] == [0, 127]


def test_actions_are_routed_to_independent_tracks():
    """Compilation preserves the destination of every multi-track action."""

    specs = (
        discrete_pitch("bass", [36, 38, 40], id="bass_pitch"),
        continuous_pitch("lead", 60.0, 84.0, id="lead_pitch"),
    )
    commands = compile_actions(
        {"bass_pitch": 1, "lead_pitch": np.array([72.25])}, specs
    )

    assert [(command.track_id, command.values["value"]) for command in commands] == [
        ("bass", 38),
        ("lead", [72.25]),
    ]


def test_trigger_and_multi_discrete_spaces():
    """One-shot and compound categorical controls receive suitable spaces."""

    specs = (
        ActionSpec(
            id="retrigger",
            track_id="agent",
            target="midi.note_retrigger",
            representation=ActionRepresentation.TRIGGER,
            update_mode=UpdateMode.TRIGGER,
        ),
        ActionSpec(
            id="chord",
            track_id="agent",
            target="musical.chord",
            representation=ActionRepresentation.MULTI_DISCRETE,
            dimensions=(("C", "D", "E"), ("major", "minor"), (0, 1, 2)),
        ),
    )
    space = build_action_space(specs)
    assert isinstance(space["retrigger"], spaces.MultiBinary)
    assert isinstance(space["chord"], spaces.MultiDiscrete)

    commands = compile_actions(
        {"retrigger": np.array([1]), "chord": np.array([1, 0, 2])}, specs
    )
    assert commands[0].values["value"] == [1]
    assert commands[1].values["value"] == ["D", "major", 2]
