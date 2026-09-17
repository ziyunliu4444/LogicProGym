"""Payload construction and required-field validation for protocol v1."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from logicprogym.protocol.types import (
    CURRENT_VERSION,
    Envelope,
    FrameFlags,
    MessageType,
    ProtocolVersion,
)


REQUIRED_FIELDS: dict[MessageType, frozenset[str]] = {
    MessageType.HELLO: frozenset({"role", "versions", "build", "max_payload"}),
    MessageType.WELCOME: frozenset(
        {"session_id", "version", "heartbeat_ms", "max_payload"}
    ),
    MessageType.REJECT: frozenset({"code", "message"}),
    MessageType.HEARTBEAT: frozenset({"last_received_sequence"}),
    MessageType.REGISTER_INSTANCE: frozenset(
        {"instance_id", "runtime_id", "name", "plugin", "capabilities", "controls"}
    ),
    MessageType.UNREGISTER_INSTANCE: frozenset({"instance_id", "reason"}),
    MessageType.WORLD_DESCRIPTION: frozenset({"world"}),
    MessageType.WORLD_UPDATE: frozenset({"changes"}),
    MessageType.COMMAND_BATCH: frozenset({"instance_id", "commands"}),
    MessageType.EVENT_BATCH: frozenset({"instance_id", "events"}),
    MessageType.STATE_SNAPSHOT: frozenset({"instance_id", "transport", "controls"}),
    MessageType.RESET_REQUEST: frozenset({"episode_id", "state_policy"}),
    MessageType.RESET_ACK: frozenset({"episode_id", "instance_id", "status"}),
    MessageType.ALL_NOTES_OFF: frozenset({"instance_ids"}),
    MessageType.ERROR: frozenset({"code", "message", "fatal"}),
}


def negotiate_version(
    peer_min: ProtocolVersion,
    peer_max: ProtocolVersion,
    *,
    local_min: ProtocolVersion = CURRENT_VERSION,
    local_max: ProtocolVersion = CURRENT_VERSION,
) -> ProtocolVersion:
    """Choose the greatest mutually supported version or reject the peer."""

    if peer_min > peer_max or local_min > local_max:
        raise ValueError("Protocol version ranges are invalid")
    if peer_max.major < local_min.major or local_max.major < peer_min.major:
        raise ValueError("No compatible protocol major version")
    major = min(peer_max.major, local_max.major)
    if major != max(peer_min.major, local_min.major):
        raise ValueError("Version ranges span unsupported protocol majors")
    minimum_minor = max(
        peer_min.minor if peer_min.major == major else 0,
        local_min.minor if local_min.major == major else 0,
    )
    maximum_minor = min(
        peer_max.minor if peer_max.major == major else 255,
        local_max.minor if local_max.major == major else 255,
    )
    if minimum_minor > maximum_minor:
        raise ValueError("No compatible protocol minor version")
    return ProtocolVersion(major, maximum_minor)


def hello_payload(
    *,
    role: str,
    build: dict[str, Any],
    minimum: ProtocolVersion = CURRENT_VERSION,
    maximum: ProtocolVersion = CURRENT_VERSION,
    max_payload: int = 1024 * 1024,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Build the first payload sent by a bridge or server peer."""

    payload: dict[str, Any] = {
        "role": role,
        "versions": {
            "minimum": {"major": minimum.major, "minor": minimum.minor},
            "maximum": {"major": maximum.major, "minor": maximum.minor},
        },
        "build": dict(build),
        "max_payload": max_payload,
    }
    if auth_token is not None:
        payload["auth_token"] = auth_token
    return payload


def batch_payload(
    message_type: MessageType,
    instance_id: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a command or event batch with its stable plugin instance target."""

    if message_type is MessageType.COMMAND_BATCH:
        key = "commands"
    elif message_type is MessageType.EVENT_BATCH:
        key = "events"
    else:
        raise ValueError("Batch payload supports only commands or events")
    return {"instance_id": instance_id, key: items}


def validate_payload(message_type: MessageType, payload: Mapping[str, Any]) -> None:
    """Validate required v1 fields and foundational batch invariants."""

    missing = REQUIRED_FIELDS[message_type] - payload.keys()
    if missing:
        raise ValueError(
            f"{message_type.name} payload is missing: {', '.join(sorted(missing))}"
        )
    if message_type in {MessageType.COMMAND_BATCH, MessageType.EVENT_BATCH}:
        key = "commands" if message_type is MessageType.COMMAND_BATCH else "events"
        if not isinstance(payload[key], list):
            raise ValueError(f"{key} must be a JSON array")
        for index, item in enumerate(payload[key]):
            if not isinstance(item, dict) or "kind" not in item:
                raise ValueError(f"{key}[{index}] must be an object containing kind")


def make_envelope(
    message_type: MessageType,
    sequence: int,
    payload: Mapping[str, Any],
    *,
    timestamp_samples: int = -1,
    flags: FrameFlags = FrameFlags.NONE,
    version: ProtocolVersion = CURRENT_VERSION,
) -> Envelope:
    """Validate and construct one immutable protocol envelope."""

    validate_payload(message_type, payload)
    return Envelope(
        message_type=message_type,
        sequence=sequence,
        payload=dict(payload),
        timestamp_samples=timestamp_samples,
        flags=flags,
        version=version,
    )
