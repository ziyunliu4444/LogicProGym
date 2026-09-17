"""Shared human-agent behavior of the backend-neutral music world."""

import numpy as np
import pytest

from logicprogym.actions.presets import notes_only, world_control
from logicprogym.backends.base import MusicBackend
from logicprogym.backends.standalone import StandaloneBackend
from logicprogym.env import LogicProEnv
from logicprogym.models import DawCommand, EventSource, TrackDescriptor
from logicprogym.world import (
    AccessPolicy,
    ConflictPolicy,
    ControlDescriptor,
    MusicWorldDescription,
    ParticipantDescriptor,
    ParticipantRole,
)


def _world() -> MusicWorldDescription:
    return MusicWorldDescription(
        id="shared-lab",
        name="Shared Music Lab",
        tracks=(
            TrackDescriptor("human", "Human"),
            TrackDescriptor("agent", "Agent"),
            TrackDescriptor("shared", "Shared Synth"),
        ),
        controls=(
            ControlDescriptor(
                "shared/cutoff",
                "shared",
                "Filter Cutoff",
                default=0.5,
                conflict=ConflictPolicy.HUMAN_PRIORITY,
            ),
            ControlDescriptor(
                "shared/master_volume",
                "shared",
                "Master Volume",
                default=0.8,
                access=AccessPolicy.HUMAN_ONLY,
            ),
        ),
        participants=(
            ParticipantDescriptor("performer", "Performer", ParticipantRole.HUMAN),
            ParticipantDescriptor("policy", "Policy", ParticipantRole.AGENT),
        ),
    )


def test_standalone_backend_implements_general_music_backend():
    backend = StandaloneBackend(_world())
    assert isinstance(backend, MusicBackend)
    assert backend.discover_world().id == "shared-lab"


def test_human_and_agent_events_share_one_timestamped_world():
    backend = StandaloneBackend(_world())
    backend.connect()
    backend.inject_human_event("human", "note_on", {"note": 60, "velocity": 0.7})
    backend.apply(
        [
            DawCommand(
                "agent",
                "midi.note_on",
                {"note": 48, "velocity": 0.8},
                command_id="agent-note",
            )
        ]
    )
    snapshot = backend.observe()
    assert [event.source for event in snapshot.events] == [
        EventSource.HUMAN,
        EventSource.AGENT,
    ]
    assert {event.timestamp_samples for event in snapshot.events} == {0}


def test_human_priority_and_human_only_controls_are_enforced():
    backend = StandaloneBackend(_world())
    backend.connect()
    backend.set_human_control("shared/cutoff", 0.9)
    backend.apply(
        [
            DawCommand(
                "shared",
                "world.control.set",
                {"control_id": "shared/cutoff", "value": 0.1},
            )
        ]
    )
    assert backend.observe().parameter_values["shared/cutoff"] == 0.9

    with pytest.raises(PermissionError, match="human_only"):
        backend.apply(
            [
                DawCommand(
                    "shared",
                    "world.control.set",
                    {"control_id": "shared/master_volume", "value": 0.2},
                )
            ]
        )


def test_gymnasium_environment_runs_on_standalone_world():
    actions = notes_only("agent") + (
        world_control(
            "shared", "shared/cutoff", id="shared/cutoff", smoothing_ms=20
        ),
    )
    env = LogicProEnv(
        StandaloneBackend(_world()),
        actions,
        max_tracks=3,
        max_parameters=2,
        observed_fields=("human.notes", "transport.beat"),
    )
    observation, _ = env.reset()
    action = env.action_space.sample()
    action["note_gate"] = np.zeros(128, dtype=np.int8)
    action["note_gate"][48] = 1
    action["velocity"] = np.full(128, 0.75, dtype=np.float32)
    action["shared/cutoff"] = np.asarray([0.25], dtype=np.float32)
    observation, _, _, _, info = env.step(action)

    assert env.observation_space.contains(observation)
    assert info["snapshot"].parameter_values["shared/cutoff"] == 0.25
    assert any(event.kind == "note_on" for event in info["snapshot"].events)
    env.close()
