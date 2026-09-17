"""Tests for stable multi-track, multi-parameter observation encoding."""

from logicprogym.models import (
    DawEvent,
    DawSnapshot,
    EventSource,
    ParameterDescriptor,
    TrackDescriptor,
)
from logicprogym.observations import EVENT_KIND_CODES, ObservationBuilder
from logicprogym.registry import SessionRegistry


def _registry() -> SessionRegistry:
    registry = SessionRegistry(max_tracks=4, max_parameters=8)
    registry.bind(
        [TrackDescriptor("human", "Human"), TrackDescriptor("agent", "Agent")],
        [ParameterDescriptor("agent/cutoff", "agent", "Cutoff")],
    )
    return registry


def test_human_note_event_updates_provenance_and_active_note_state():
    builder = ObservationBuilder(_registry(), event_capacity=4)
    snapshot = DawSnapshot(
        events=(
            DawEvent(
                timestamp_samples=512,
                track_id="human",
                source=EventSource.HUMAN,
                kind="note_on",
                values={"note": 60, "velocity": 0.8},
            ),
        )
    )

    observation = builder.build(snapshot)
    assert observation["events"][0, 1] == 0  # Human track slot.
    assert observation["events"][0, 2] == 0  # Human source code.
    assert observation["events"][0, 3] == EVENT_KIND_CODES["note_on"]
    assert observation["active_notes"][0, 60, 0] == 1
    assert observation["active_notes"][0, 60, 1] == 0.8


def test_agent_echo_is_identifiable_and_note_off_clears_state():
    builder = ObservationBuilder(_registry(), event_capacity=4)
    builder.build(
        DawSnapshot(
            events=(
                DawEvent(
                    1,
                    "agent",
                    EventSource.AGENT,
                    "note_on",
                    {"note": 64, "velocity": 1.0},
                    command_id="command-1",
                ),
            )
        )
    )
    observation = builder.build(
        DawSnapshot(
            events=(DawEvent(2, "agent", EventSource.AGENT, "note_off", {"note": 64}),)
        )
    )
    assert observation["active_notes"][1, 64, 0] == 0


def test_parameter_values_use_stable_discovery_slots():
    builder = ObservationBuilder(_registry(), event_capacity=4)
    observation = builder.build(
        DawSnapshot(parameter_values={"agent/cutoff": 0.75})
    )
    assert observation["parameter_values"][0] == 0.75
    assert observation["parameter_mask"].tolist() == [1, 0, 0, 0, 0, 0, 0, 0]


def test_event_history_survives_a_later_empty_snapshot():
    builder = ObservationBuilder(_registry(), event_capacity=2)
    builder.build(
        DawSnapshot(
            events=(
                DawEvent(
                    10,
                    "human",
                    EventSource.HUMAN,
                    "note_on",
                    {"note": 60, "velocity": 0.5},
                ),
            )
        )
    )
    observation = builder.build(DawSnapshot())
    assert observation["event_mask"].tolist() == [1, 0]
    assert observation["events"][0, 4] == 60
