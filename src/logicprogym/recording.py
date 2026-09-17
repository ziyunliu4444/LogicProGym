"""Record and deterministically replay canonical adapter traffic as JSON Lines."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.models import (
    DawCommand,
    DawEvent,
    DawSnapshot,
    EventSource,
    ParameterDescriptor,
    TrackDescriptor,
    TransportState,
)


def _event_dict(event: DawEvent) -> dict[str, Any]:
    return {
        "timestamp_samples": event.timestamp_samples,
        "track_id": event.track_id,
        "source": event.source.value,
        "kind": event.kind,
        "values": event.values,
        "command_id": event.command_id,
    }


def _snapshot_dict(snapshot: DawSnapshot) -> dict[str, Any]:
    return {
        "transport": snapshot.transport.__dict__,
        "events": [_event_dict(event) for event in snapshot.events],
        "parameter_values": snapshot.parameter_values,
        "diagnostics": snapshot.diagnostics,
    }


def _snapshot_from_dict(raw: dict[str, Any]) -> DawSnapshot:
    return DawSnapshot(
        transport=TransportState(**raw["transport"]),
        events=tuple(
            DawEvent(
                timestamp_samples=event["timestamp_samples"],
                track_id=event["track_id"],
                source=EventSource(event["source"]),
                kind=event["kind"],
                values=event.get("values", {}),
                command_id=event.get("command_id"),
            )
            for event in raw.get("events", ())
        ),
        parameter_values=dict(raw.get("parameter_values", {})),
        diagnostics=dict(raw.get("diagnostics", {})),
    )


class RecordingAdapter(LogicProAdapter):
    """Transparent adapter wrapper that records discovery, actions, and snapshots."""

    def __init__(self, adapter: LogicProAdapter, path: str | Path) -> None:
        self.adapter = adapter
        self.path = Path(path)
        self.capabilities = adapter.capabilities
        self._stream = None

    def _write(self, kind: str, payload: Any) -> None:
        if self._stream is None:
            raise RuntimeError("Recording adapter is not connected")
        self._stream.write(json.dumps({"type": kind, "payload": payload}) + "\n")
        # Flush each record so interrupted real-time sessions remain recoverable.
        self._stream.flush()

    def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("w", encoding="utf-8")
        try:
            self.adapter.connect()
        except Exception:
            self._stream.close()
            self._stream = None
            raise

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        discovered_tracks, discovered_parameters = self.adapter.discover()
        # Normalize arbitrary adapter sequences so recording and replay expose the
        # same deterministic container types.
        tracks = tuple(discovered_tracks)
        parameters = tuple(discovered_parameters)
        self._write(
            "session",
            {
                "tracks": [
                    {**track.__dict__, "capabilities": sorted(track.capabilities)}
                    for track in tracks
                ],
                "parameters": [parameter.__dict__ for parameter in parameters],
            },
        )
        return tracks, parameters

    def receive(self) -> DawSnapshot:
        snapshot = self.adapter.receive()
        self._write("snapshot", _snapshot_dict(snapshot))
        return snapshot

    def send(self, commands: Sequence[DawCommand]) -> None:
        self._write("commands", [command.__dict__ for command in commands])
        self.adapter.send(commands)

    def close(self) -> None:
        try:
            self.adapter.close()
        finally:
            if self._stream is not None:
                self._stream.close()
                self._stream = None


class ReplayAdapter(LogicProAdapter):
    """Read-only adapter that returns snapshots from a prior recording."""

    capabilities = AdapterCapabilities(
        human_events=True,
        agent_output=False,
        multiple_tracks=True,
        transport_read=True,
        mixer_parameters=True,
        plugin_parameters=True,
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._tracks: tuple[TrackDescriptor, ...] = ()
        self._parameters: tuple[ParameterDescriptor, ...] = ()
        self._snapshots: list[DawSnapshot] = []
        self._position = 0
        self.received_actions: list[tuple[DawCommand, ...]] = []

    def connect(self) -> None:
        """Load and validate the complete recording before replay begins."""

        session_seen = False
        self._snapshots.clear()
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                record = json.loads(line)
                if record["type"] == "session":
                    payload = record["payload"]
                    self._tracks = tuple(
                        TrackDescriptor(
                            id=track["id"],
                            name=track["name"],
                            capabilities=frozenset(track.get("capabilities", ())),
                        )
                        for track in payload.get("tracks", ())
                    )
                    self._parameters = tuple(
                        ParameterDescriptor(**parameter)
                        for parameter in payload.get("parameters", ())
                    )
                    session_seen = True
                elif record["type"] == "snapshot":
                    self._snapshots.append(_snapshot_from_dict(record["payload"]))
                elif record["type"] not in {"commands"}:
                    raise ValueError(
                        f"Unknown recording entry on line {line_number}: {record['type']!r}"
                    )
        if not session_seen:
            raise ValueError("Recording has no session discovery record")
        self._position = 0

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        return self._tracks, self._parameters

    def receive(self) -> DawSnapshot:
        if self._position >= len(self._snapshots):
            raise EOFError("DAW recording is exhausted")
        snapshot = self._snapshots[self._position]
        self._position += 1
        return snapshot

    def send(self, commands: Sequence[DawCommand]) -> None:
        """Capture replay-time actions without producing external side effects."""

        self.received_actions.append(tuple(commands))

    def close(self) -> None:
        return None
