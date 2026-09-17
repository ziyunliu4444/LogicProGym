"""Binary framing and incremental stream decoding for bridge messages."""

from __future__ import annotations

import json
import struct

from logicprogym.protocol.types import (
    CURRENT_VERSION,
    DEFAULT_MAX_PAYLOAD,
    MAGIC,
    Envelope,
    FrameFlags,
    MessageType,
    ProtocolVersion,
)


HEADER = struct.Struct("!4sBBHHHIQq")
HEADER_SIZE = HEADER.size


class ProtocolError(ValueError):
    """Malformed, unsupported, or unsafe bridge frame."""


def encode_frame(envelope: Envelope, *, max_payload: int = DEFAULT_MAX_PAYLOAD) -> bytes:
    """Serialize one envelope into a complete framed byte sequence."""

    try:
        payload = json.dumps(
            envelope.payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProtocolError(f"Payload is not valid JSON: {error}") from error
    if len(payload) > max_payload:
        raise ProtocolError(
            f"Payload length {len(payload)} exceeds negotiated limit {max_payload}"
        )
    header = HEADER.pack(
        MAGIC,
        envelope.version.major,
        envelope.version.minor,
        int(envelope.message_type),
        int(envelope.flags),
        0,
        len(payload),
        envelope.sequence,
        envelope.timestamp_samples,
    )
    return header + payload


def decode_frame(frame: bytes, *, max_payload: int = DEFAULT_MAX_PAYLOAD) -> Envelope:
    """Decode exactly one complete frame, rejecting trailing or unsafe data."""

    if len(frame) < HEADER_SIZE:
        raise ProtocolError("Frame is shorter than the 32-byte header")
    magic, major, minor, raw_type, raw_flags, reserved, length, sequence, timestamp = (
        HEADER.unpack_from(frame)
    )
    if magic != MAGIC:
        raise ProtocolError("Invalid bridge protocol magic")
    if reserved != 0:
        raise ProtocolError("Reserved header field must be zero")
    if major != CURRENT_VERSION.major:
        raise ProtocolError(
            f"Unsupported protocol major {major}; expected {CURRENT_VERSION.major}"
        )
    if length > max_payload:
        raise ProtocolError(f"Frame payload exceeds limit {max_payload}")
    if len(frame) != HEADER_SIZE + length:
        raise ProtocolError("Frame length does not match its header")
    try:
        message_type = MessageType(raw_type)
    except ValueError as error:
        raise ProtocolError(f"Unknown message type {raw_type}") from error
    known_flags = int(FrameFlags.RESPONSE | FrameFlags.ACK_REQUIRED | FrameFlags.URGENT)
    if raw_flags & ~known_flags:
        raise ProtocolError(f"Unknown frame flags {raw_flags}")
    flags = FrameFlags(raw_flags)
    try:
        payload = json.loads(frame[HEADER_SIZE:].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError(f"Invalid UTF-8 JSON payload: {error}") from error
    if not isinstance(payload, dict):
        raise ProtocolError("Top-level payload must be a JSON object")
    return Envelope(
        message_type=message_type,
        sequence=sequence,
        payload=payload,
        timestamp_samples=timestamp,
        flags=flags,
        version=ProtocolVersion(major, minor),
    )


class FrameDecoder:
    """Reassemble arbitrary stream chunks into ordered protocol envelopes."""

    def __init__(self, *, max_payload: int = DEFAULT_MAX_PAYLOAD) -> None:
        self.max_payload = max_payload
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Envelope]:
        """Consume a byte chunk and return every complete frame now available."""

        self._buffer.extend(data)
        envelopes: list[Envelope] = []
        while len(self._buffer) >= HEADER_SIZE:
            header = HEADER.unpack_from(self._buffer)
            if header[0] != MAGIC:
                raise ProtocolError("Invalid bridge protocol magic")
            payload_length = header[6]
            if payload_length > self.max_payload:
                raise ProtocolError(
                    f"Frame payload exceeds limit {self.max_payload}"
                )
            frame_length = HEADER_SIZE + payload_length
            if len(self._buffer) < frame_length:
                break
            frame = bytes(self._buffer[:frame_length])
            del self._buffer[:frame_length]
            envelopes.append(decode_frame(frame, max_payload=self.max_payload))
        return envelopes

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)


class SequenceTracker:
    """Reject duplicate, decreasing, or gapped peer sequence numbers."""

    def __init__(self) -> None:
        self.last_sequence: int | None = None

    def accept(self, sequence: int) -> None:
        if self.last_sequence is None:
            self.last_sequence = sequence
            return
        expected = self.last_sequence + 1
        if sequence != expected:
            raise ProtocolError(
                f"Unexpected sequence {sequence}; expected {expected}"
            )
        self.last_sequence = sequence
