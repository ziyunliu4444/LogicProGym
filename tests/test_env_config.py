"""Integration tests from YAML configuration through Gymnasium construction."""

from collections.abc import Sequence

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv
from logicprogym.models import DawSnapshot, ParameterDescriptor, TrackDescriptor


class ConfigAdapter(LogicProAdapter):
    capabilities = AdapterCapabilities(
        human_events=True,
        agent_output=True,
        multiple_tracks=True,
        plugin_parameters=True,
    )

    def connect(self):
        pass

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        return [TrackDescriptor("human", "Human"), TrackDescriptor("agent", "Agent")], []

    def receive(self):
        return DawSnapshot()

    def send(self, commands):
        pass

    def close(self):
        pass


def test_environment_can_be_constructed_directly_from_yaml_config():
    config = LogicProGymConfig.from_yaml("tests/fixtures/configs/logic_basic.yaml")
    env = LogicProEnv.from_config(ConfigAdapter(), config)
    assert "agent/note_gate" in env.action_space.spaces
    assert "agent/brightness" in env.action_space.spaces
    observation, _ = env.reset()
    assert env.observation_space.contains(observation)
    env.close()
