"""End-to-end tests for the combined human-MIDI and Mackie Gym backend."""

from pathlib import Path

import mido

from logicprogym.adapters.logic_hybrid import LogicHybridAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv
from logicprogym.spaces import build_action_space
from tests.fixtures.legacy.logic_split_tracks_test import agent_action


class Port:
    def __init__(self, callback=None) -> None:
        self.callback = callback
        self.messages = []

    def send(self, message) -> None:
        self.messages.append(message)

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.close()


class HumanMidiBackend:
    Message = mido.Message

    def __init__(self) -> None:
        self.inputs = []

    def open_input(self, _name, callback=None):
        port = Port(callback)
        self.inputs.append(port)
        return port

    def open_output(self, _name):
        return Port()


class MackieMidiBackend:
    def __init__(self) -> None:
        self.inputs = []
        self.outputs = []

    def open_input(self, _name, virtual=False, callback=None):
        assert virtual
        port = Port(callback)
        self.inputs.append(port)
        return port

    def open_output(self, _name, virtual=False):
        assert virtual
        port = Port()
        self.outputs.append(port)
        return port


def test_hybrid_env_observes_human_and_controls_two_tracks() -> None:
    path = Path(__file__).parents[1] / "tests" / "fixtures" / "configs" / "logic_hybrid_gym_test.yaml"
    config = LogicProGymConfig.from_yaml(path)
    human_backend = HumanMidiBackend()
    mackie_backend = MackieMidiBackend()
    raw = {
        **config.adapter,
        "mackie": {**config.adapter["mackie"], "inter_message_delay": 0},
    }
    adapter = LogicHybridAdapter.from_config(
        raw,
        midi_backend=human_backend,
        mackie_backend=mackie_backend,
    )
    env = LogicProEnv.from_config(adapter, config)
    try:
        observation, _info = env.reset()
        assert observation["track_mask"].sum() == 3
        human_backend.inputs[0].callback(
            mido.Message("note_on", note=60, velocity=100)
        )
        action = {
            "track_1/parameter_vector": [0.5, 0.0, 0.0],
            "track_2/parameter_vector": [0.0, -0.5, 0.0],
        }
        observation, _reward, _terminated, _truncated, info = env.step(action)
        assert observation["event_mask"].sum() == 1
        assert info["snapshot"].events[0].track_id == "human"
        assert info["snapshot"].events[0].values["note"] == 60
        assert any(message.type == "control_change" for message in mackie_backend.outputs[0].messages)
        assert any(message.type == "control_change" for message in mackie_backend.outputs[1].messages)
    finally:
        env.close()


def test_focused_shared_and_split_test_action_schemas_are_valid() -> None:
    root = Path(__file__).parents[1]
    shared = LogicProGymConfig.from_yaml(root / "tests" / "fixtures" / "configs" / "logic_shared_track_test.yaml")
    assert [spec.id for spec in shared.actions] == ["shared/parameter_vector"]
    assert shared.actions[0].shape == (8,)
    assert len(shared.actions[0].encoding["parameters"]) == 8
    split = LogicProGymConfig.from_yaml(root / "tests" / "fixtures" / "configs" / "logic_split_tracks_test.yaml")
    space = build_action_space(split.actions)
    assert space.contains(agent_action(step=0, control_hz=4.0))
