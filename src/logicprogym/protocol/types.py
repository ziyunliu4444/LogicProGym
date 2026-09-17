"""Wire-level constants and immutable bridge envelope types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Any


MAGIC = b"DGYP"
DEFAULT_MAX_PAYLOAD = 1024 * 1024


@dataclass(frozen=True, order=True)
class ProtocolVersion:
    major: int
    minor: int

    def __post_init__(self) -> None:
        if not 0 <= self.major <= 255 or not 0 <= self.minor <= 255:
            raise ValueError("Protocol version components must fit uint8")


CURRENT_VERSION = ProtocolVersion(1, 0)


class MessageType(IntEnum):
    HELLO = 1
    WELCOME = 2
    REJECT = 3
    HEARTBEAT = 4
    REGISTER_INSTANCE = 10
    UNREGISTER_INSTANCE = 11
    WORLD_DESCRIPTION = 12
    WORLD_UPDATE = 13
    COMMAND_BATCH = 20
    EVENT_BATCH = 21
    STATE_SNAPSHOT = 22
    RESET_REQUEST = 30
    RESET_ACK = 31
    ALL_NOTES_OFF = 32
    ERROR = 255


class FrameFlags(IntFlag):
    NONE = 0
    RESPONSE = 1 << 0
    ACK_REQUIRED = 1 << 1
    URGENT = 1 << 2


@dataclass(frozen=True)
class Envelope:
    """One decoded protocol frame and its JSON-compatible payload."""

    message_type: MessageType
    sequence: int
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp_samples: int = -1
    flags: FrameFlags = FrameFlags.NONE
    version: ProtocolVersion = CURRENT_VERSION

    def __post_init__(self) -> None:
        if not 0 <= self.sequence <= (2**64 - 1):
            raise ValueError("Sequence must fit uint64")
        if not -(2**63) <= self.timestamp_samples <= (2**63 - 1):
            raise ValueError("Sample timestamp must fit int64")
