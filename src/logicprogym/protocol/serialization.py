"""Canonical JSON payloads for music-world descriptions, commands, and events."""

from __future__ import annotations

from typing import Any

from logicprogym.models import DawCommand, DawEvent, DawSnapshot
from logicprogym.world import MusicWorldDescription


def world_payload(world: MusicWorldDescription) -> dict[str, Any]:
    """Serialize the discoverable shared world without backend-specific objects."""

    return {
        "id": world.id,
        "name": world.name,
        "tracks": [
            {
                "id": track.id,
                "name": track.name,
                "capabilities": sorted(track.capabilities),
            }
            for track in world.tracks
        ],
        "devices": [
            {
                "id": device.id,
                "track_id": device.track_id,
                "name": device.name,
                "kind": device.kind,
                "capabilities": sorted(device.capabilities),
            }
            for device in world.devices
        ],
        "controls": [
            {
                "id": control.id,
                "track_id": control.track_id,
                "device_id": control.device_id,
                "name": control.name,
                "kind": control.kind.value,
                "minimum": control.minimum,
                "maximum": control.maximum,
                "default": control.default,
                "values": list(control.values),
                "writable": control.writable,
                "access": control.access.value,
                "conflict": control.conflict.value,
                "metadata": control.metadata,
            }
            for control in world.controls
        ],
        "participants": [
            {
                "id": participant.id,
                "name": participant.name,
                "role": participant.role.value,
            }
            for participant in world.participants
        ],
        "routes": [
            {
                "source_id": route.source_id,
                "destination_id": route.destination_id,
                "kind": route.kind,
            }
            for route in world.routes
        ],
        "metadata": world.metadata,
    }


def command_payload(command: DawCommand) -> dict[str, Any]:
    """Serialize a canonical command while preserving its echo identity."""

    return {
        "command_id": command.command_id,
        "track_id": command.track_id,
        "kind": command.kind,
        "values": command.values,
        "timestamp_samples": command.timestamp_samples,
    }


def event_payload(event: DawEvent) -> dict[str, Any]:
    """Serialize event provenance and DAW sample timing losslessly."""

    return {
        "timestamp_samples": event.timestamp_samples,
        "track_id": event.track_id,
        "source": event.source.value,
        "kind": event.kind,
        "values": event.values,
        "command_id": event.command_id,
    }


def snapshot_payload(snapshot: DawSnapshot, instance_id: str) -> dict[str, Any]:
    """Serialize one synchronized state snapshot for recording or transport."""

    return {
        "instance_id": instance_id,
        "transport": {
            "sample_position": snapshot.transport.sample_position,
            "sample_rate": snapshot.transport.sample_rate,
            "tempo": snapshot.transport.tempo,
            "beat_position": snapshot.transport.beat_position,
            "playing": snapshot.transport.playing,
        },
        "controls": dict(snapshot.parameter_values),
        "events": [event_payload(event) for event in snapshot.events],
        "diagnostics": dict(snapshot.diagnostics),
    }
