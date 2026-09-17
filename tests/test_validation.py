"""Tests for rejecting experiments an adapter cannot actually execute."""

import pytest

from logicprogym.actions.presets import continuous_pitch
from logicprogym.actions.specs import ActionRepresentation, ActionSpec
from logicprogym.adapters.base import AdapterCapabilities
from logicprogym.adapters.logic import LogicMidiAdapter
from logicprogym.validation import validate_capabilities


def test_logic_midi_accepts_multitrack_musical_output():
    actions = [
        continuous_pitch("bass", 36, 60, id="bass_pitch"),
        continuous_pitch("lead", 60, 84, id="lead_pitch"),
    ]
    validate_capabilities(LogicMidiAdapter.capabilities, actions)


def test_logic_midi_rejects_arbitrary_plugin_parameter_control():
    action = ActionSpec(
        id="brightness",
        track_id="agent",
        target="plugin.parameter",
        representation=ActionRepresentation.CONTINUOUS,
    )
    with pytest.raises(ValueError, match="plugin_parameters"):
        validate_capabilities(LogicMidiAdapter.capabilities, [action])


def test_transport_observation_requires_transport_capability():
    with pytest.raises(ValueError, match="transport_read"):
        validate_capabilities(
            AdapterCapabilities(human_events=True), [], ["transport.beat"]
        )
