"""Tests for addressed multi-track Mackie control infrastructure."""

import mido
import pytest
from pathlib import Path

from logicprogym.adapters.logic_mackie import (
    LogicMackieBridge,
    LogicMackieAdapter,
    LogicMackieTrack,
    LogicMackieProfile,
    LogicMackieService,
    MackieParameterAddress,
    MackieRelativeAction,
)
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv


class FakeOutput:
    def __init__(self) -> None:
        self.messages: list[mido.Message] = []

    def send(self, message: mido.Message) -> None:
        self.messages.append(message)

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return None


class FakeInput(FakeOutput):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback


class FakeMidiBackend:
    def __init__(self) -> None:
        self.outputs: list[FakeOutput] = []
        self.inputs: list[FakeInput] = []

    def open_output(self, _name: str, virtual: bool = False):
        assert virtual
        port = FakeOutput()
        self.outputs.append(port)
        return port

    def open_input(self, _name: str, virtual: bool = False, callback=None):
        assert virtual
        port = FakeInput(callback)
        self.inputs.append(port)
        return port


def action(track: str, page: int = 1, slot: int = 1, steps: int = 1):
    return MackieRelativeAction(MackieParameterAddress(track, page, slot), steps)


def test_pinned_tracks_use_independent_controllers() -> None:
    outputs = [FakeOutput(), FakeOutput()]
    bridge = LogicMackieBridge(
        outputs,
        [
            LogicMackieTrack("synth", logic_track=1, controller=1),
            LogicMackieTrack("trombone", logic_track=2, controller=2),
        ],
    )
    assert bridge.apply_relative(action("synth", slot=2)) == 1
    assert bridge.apply_relative(action("trombone", slot=3)) == 2
    assert outputs[0].messages[-1].control == 0x11
    assert outputs[1].messages[-1].control == 0x12


def test_action_restores_track_and_navigates_from_feedback_page() -> None:
    output = FakeOutput()
    bridge = LogicMackieBridge([output], [LogicMackieTrack("synth", logic_track=2)])
    bridge.track_pages["synth"] = 2
    controller, messages = bridge.messages_for(action("synth", page=4, slot=8, steps=-2))
    assert controller == 1
    assert messages[0].note == 0x19  # Select track slot 2.
    assert sum(message.note == 0x63 for message in messages if message.type == "note_on") == 4
    assert messages[-1].type == "control_change"
    assert (messages[-1].control, messages[-1].value) == (0x17, 0x42)


def test_nonfirst_page_requires_observed_page_state() -> None:
    bridge = LogicMackieBridge([FakeOutput()], [LogicMackieTrack("synth", 1)])
    with pytest.raises(RuntimeError, match="Current page"):
        bridge.messages_for(action("synth", page=2))


def test_batch_activates_track_once_and_turns_multiple_vpots() -> None:
    output = FakeOutput()
    bridge = LogicMackieBridge([output], [LogicMackieTrack("synth", 1)])
    assignments = bridge.apply_batch(
        [action("synth", slot=1, steps=2), action("synth", slot=6, steps=-3)]
    )
    assert assignments == {"synth": 1}
    select_presses = [
        message
        for message in output.messages
        if message.type == "note_on" and message.note == 0x18 and message.velocity > 0
    ]
    assert len(select_presses) == 1
    turns = [message for message in output.messages if message.type == "control_change"]
    assert [(message.control, message.value) for message in turns] == [
        (0x10, 2),
        (0x15, 0x43),
    ]


def test_batch_can_restore_human_track_selection() -> None:
    output = FakeOutput()
    bridge = LogicMackieBridge(
        [output],
        [LogicMackieTrack("agent", 1)],
        restore_logic_track=3,
    )
    bridge.apply_batch([action("agent")])
    assert (output.messages[-2].note, output.messages[-2].velocity) == (0x1A, 0x7F)
    assert (output.messages[-1].note, output.messages[-1].velocity) == (0x1A, 0)


def test_lcd_feedback_updates_per_track_page_and_display() -> None:
    bridge = LogicMackieBridge([FakeOutput()], [LogicMackieTrack("synth", 1)])
    bridge.messages_for(action("synth"))
    text = 'Track 1 "Alchemy" Page 3/71'.ljust(56) + "Robotc"
    message = mido.Message("sysex", data=(0, 0, 0x66, 0x14, 0x12, 0, *map(ord, text)))
    assert bridge.ingest(1, message)
    assert bridge.track_pages["synth"] == 3
    assert bridge.parameters("synth")[0][1] == "Robotc"


def test_pool_rejects_two_tracks_pinned_to_one_controller() -> None:
    with pytest.raises(ValueError, match="Only one track"):
        LogicMackieBridge(
            [FakeOutput()],
            [LogicMackieTrack("one", 1, 1), LogicMackieTrack("two", 2, 1)],
        )


def test_profile_and_service_own_two_virtual_pairs(tmp_path) -> None:
    profile_path = tmp_path / "logic.yaml"
    profile_path.write_text(
        """controller_count: 2
controllers:
  - controller: 1
    track: 1
    id: alchemy
  - controller: 2
    track: 2
    id: trombone
"""
    )
    profile = LogicMackieProfile.from_yaml(profile_path)
    assert [track.id for track in profile.tracks] == ["alchemy", "trombone"]
    backend = FakeMidiBackend()
    service = LogicMackieService(profile, midi_backend=backend, inter_message_delay=0)
    with service:
        assert service.connected
        assert len(backend.outputs) == len(backend.inputs) == 2
        assert service.apply_relative(action("trombone", slot=2)) == 2
        feedback = mido.Message(
            "sysex",
            data=(0, 0, 0x66, 0x14, 0x12, 0, *map(ord, "Track 2 Page 1/4")),
        )
        backend.inputs[1].callback(feedback)
        assert service.bridge.track_pages["trombone"] == 1
    assert not service.connected


def test_gym_step_routes_discrete_relative_action_to_track_two() -> None:
    config_path = Path(__file__).parents[1] / "tests" / "fixtures" / "configs" / "logic_mackie_gym_test.yaml"
    config = LogicProGymConfig.from_yaml(config_path)
    backend = FakeMidiBackend()
    adapter_config = {**config.adapter, "inter_message_delay": 0}
    adapter = LogicMackieAdapter.from_config(adapter_config, midi_backend=backend)
    env = LogicProEnv.from_config(adapter, config)
    try:
        observation, _info = env.reset()
        assert observation["track_mask"].sum() == 2
        action_values = {
            "track_1/parameter_vector": [0.0, 0.0, 0.0],
            "track_2/parameter_vector": [0.25, 0.0, -0.5],
        }
        _observation, _reward, _terminated, _truncated, info = env.step(action_values)
        assert backend.outputs[0].messages == []
        assert backend.outputs[1].messages[-1].type == "control_change"
        assert (backend.outputs[1].messages[-1].control, backend.outputs[1].messages[-1].value) == (
            0x16,
            0x44,
        )
        assert "mackie_pages" in info["snapshot"].diagnostics
    finally:
        env.close()
