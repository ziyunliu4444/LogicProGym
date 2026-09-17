"""Hardware-free tests for Logic's routed virtual-MIDI prototype."""

import mido
import pytest

from logicprogym.adapters.logic import LogicMidiAdapter, LogicMidiRoute
from logicprogym.models import DawCommand, EventSource


class FakePort:
    def __init__(self, callback=None):
        self.callback = callback
        self.messages = []
        self.closed = False

    def send(self, message):
        self.messages.append(message)

    def close(self):
        self.closed = True


class FakeMidiBackend:
    Message = mido.Message

    def __init__(self):
        self.inputs = {}
        self.outputs = {}

    def open_input(self, name, callback):
        self.inputs[name] = FakePort(callback)
        return self.inputs[name]

    def open_output(self, name):
        self.outputs[name] = FakePort()
        return self.outputs[name]

    def get_input_names(self):
        return ["Logic Human Out"]

    def get_output_names(self):
        return ["Logic Agent In"]


def _adapter():
    backend = FakeMidiBackend()
    adapter = LogicMidiAdapter(
        [
            LogicMidiRoute("human", "Human", input_port="Logic Human Out"),
            LogicMidiRoute("agent", "Agent", output_port="Logic Agent In", channel=2),
        ],
        midi_backend=backend,
    )
    adapter.connect()
    return adapter, backend


def test_logic_midi_routes_agent_notes_to_the_configured_track():
    adapter, backend = _adapter()
    adapter.send(
        [
            DawCommand(
                "agent", "midi.note_on", {"note": 64, "velocity": 0.5}
            )
        ]
    )
    message = backend.outputs["Logic Agent In"].messages[0]
    assert (message.type, message.note, message.velocity, message.channel) == (
        "note_on",
        64,
        64,
        2,
    )
    adapter.close()


def test_logic_midi_observes_human_input_with_track_provenance():
    adapter, backend = _adapter()
    backend.inputs["Logic Human Out"].callback(
        mido.Message("note_on", note=60, velocity=96)
    )
    event = adapter.receive().events[0]
    assert event.track_id == "human"
    assert event.source is EventSource.HUMAN
    assert event.kind == "note_on"
    assert event.values["note"] == 60
    adapter.close()


def test_logic_midi_refuses_non_midi_plugin_parameters():
    adapter, _ = _adapter()
    with pytest.raises(NotImplementedError, match="richer Logic bridge"):
        adapter.send(
            [
                DawCommand(
                    "agent", "plugin.parameter", {"value": [0.5], "encoding": {}}
                )
            ]
        )
    adapter.close()


def test_logic_midi_routes_can_be_loaded_and_checked_from_config():
    backend = FakeMidiBackend()
    adapter = LogicMidiAdapter.from_config(
        {
            "routes": [
                {"alias": "human", "input_port": "Logic Human Out"},
                {"alias": "agent", "output_port": "Missing Agent Port"},
            ]
        },
        midi_backend=backend,
    )
    assert adapter.check_ports() == {
        "missing_inputs": (),
        "missing_outputs": ("Missing Agent Port",),
    }
