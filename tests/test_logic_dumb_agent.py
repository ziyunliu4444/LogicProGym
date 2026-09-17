"""Offline checks for the deterministic Logic test agent's policy output."""

from pathlib import Path

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv
from logicprogym.models import DawSnapshot, TrackDescriptor

# Examples are deliberately importable so their action construction is testable
# without opening CoreMIDI or requiring Logic to be running.
from tests.fixtures.legacy.logic_dumb_agent import build_action


class OfflineAdapter(LogicProAdapter):
    capabilities = AdapterCapabilities(
        human_events=True, agent_output=True, multiple_tracks=True
    )

    def connect(self):
        pass

    def discover(self):
        return [
            TrackDescriptor("human", "Human"),
            TrackDescriptor("agent_bass", "Agent Bass"),
            TrackDescriptor("agent_lead", "Agent Lead"),
        ], []

    def receive(self):
        return DawSnapshot()

    def send(self, commands):
        pass

    def close(self):
        pass


def test_dumb_agent_builds_valid_two_track_actions():
    config = LogicProGymConfig.from_yaml(
        Path(__file__).parents[1] / "tests" / "fixtures" / "configs" / "logic_direct_test.yaml"
    )
    env = LogicProEnv.from_config(OfflineAdapter(), config)
    on = build_action(env, bass_note=36, lead_note=60, bass_gate=True, lead_gate=True)
    off = build_action(env, bass_note=36, lead_note=60, bass_gate=False, lead_gate=False)
    assert env.action_space.contains(on)
    assert env.action_space.contains(off)
    assert on["agent_bass/note_gate"][36] == 1
    assert on["agent_lead/note_gate"][60] == 1
    assert off["agent_bass/note_gate"].sum() == 0
    assert off["agent_lead/note_gate"].sum() == 0
