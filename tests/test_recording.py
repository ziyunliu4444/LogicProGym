"""Round-trip tests for deterministic DAW session recording and replay."""

from collections.abc import Sequence

from logicprogym.adapters.base import LogicProAdapter
from logicprogym.models import (
    DawCommand,
    DawEvent,
    DawSnapshot,
    EventSource,
    ParameterDescriptor,
    TrackDescriptor,
    TransportState,
)
from logicprogym.recording import RecordingAdapter, ReplayAdapter


class SourceAdapter(LogicProAdapter):
    def connect(self):
        pass

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        return [TrackDescriptor("human", "Human", frozenset({"midi_input"}))], [
            ParameterDescriptor("human/level", "human", "Level")
        ]

    def receive(self):
        return DawSnapshot(
            transport=TransportState(sample_position=256, playing=True),
            events=(
                DawEvent(
                    256,
                    "human",
                    EventSource.HUMAN,
                    "note_on",
                    {"note": 60, "velocity": 0.5},
                ),
            ),
            parameter_values={"human/level": 0.75},
            diagnostics={"queue_ms": 1.2},
        )

    def send(self, commands):
        pass

    def close(self):
        pass


def test_recorded_snapshot_and_discovery_round_trip(tmp_path):
    path = tmp_path / "session.jsonl"
    recording = RecordingAdapter(SourceAdapter(), path)
    recording.connect()
    original_discovery = recording.discover()
    original_snapshot = recording.receive()
    recording.send([DawCommand("human", "midi.note_off", {"note": 60})])
    recording.close()

    replay = ReplayAdapter(path)
    replay.connect()
    assert replay.discover() == original_discovery
    assert replay.receive() == original_snapshot


def test_replay_reports_exhaustion_instead_of_repeating_stale_state(tmp_path):
    path = tmp_path / "session.jsonl"
    recording = RecordingAdapter(SourceAdapter(), path)
    recording.connect()
    recording.discover()
    recording.receive()
    recording.close()

    replay = ReplayAdapter(path)
    replay.connect()
    replay.receive()
    try:
        replay.receive()
    except EOFError as error:
        assert "exhausted" in str(error)
    else:
        raise AssertionError("Replay should not silently repeat its last snapshot")
