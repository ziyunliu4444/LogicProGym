"""Executable compatibility contract for bridge protocol version one."""

import struct

import pytest

from logicprogym.protocol.codec import (
    HEADER_SIZE,
    FrameDecoder,
    ProtocolError,
    SequenceTracker,
    decode_frame,
    encode_frame,
)
from logicprogym.protocol.messages import (
    batch_payload,
    hello_payload,
    make_envelope,
    negotiate_version,
)
from logicprogym.protocol.serialization import command_payload, event_payload, world_payload
from logicprogym.protocol.types import (
    Envelope,
    FrameFlags,
    MessageType,
    ProtocolVersion,
)
from logicprogym.models import DawCommand, DawEvent, EventSource, TrackDescriptor
from logicprogym.world import ControlDescriptor, MusicWorldDescription


def test_header_is_fixed_32_bytes_and_frame_round_trips():
    envelope = make_envelope(
        MessageType.EVENT_BATCH,
        42,
        batch_payload(
            MessageType.EVENT_BATCH,
            "instance-1",
            [{"kind": "parameter_changed", "name": "Résonance", "value": 0.7}],
        ),
        timestamp_samples=1024,
        flags=FrameFlags.ACK_REQUIRED,
    )
    frame = encode_frame(envelope)
    assert HEADER_SIZE == 32
    assert frame[:4] == b"DGYP"
    assert decode_frame(frame) == envelope


def test_incremental_decoder_handles_partial_and_multiple_frames():
    first = encode_frame(
        Envelope(MessageType.HEARTBEAT, 1, {"last_received_sequence": 0})
    )
    second = encode_frame(
        Envelope(MessageType.HEARTBEAT, 2, {"last_received_sequence": 1})
    )
    decoder = FrameDecoder()
    assert decoder.feed(first[:7]) == []
    assert decoder.buffered_bytes == 7
    decoded = decoder.feed(first[7:] + second)
    assert [envelope.sequence for envelope in decoded] == [1, 2]
    assert decoder.buffered_bytes == 0


def test_decoder_rejects_wrong_magic_major_flags_and_trailing_data():
    frame = bytearray(
        encode_frame(Envelope(MessageType.HEARTBEAT, 0, {"last_received_sequence": 0}))
    )
    wrong_magic = bytearray(frame)
    wrong_magic[:4] = b"NOPE"
    with pytest.raises(ProtocolError, match="magic"):
        decode_frame(bytes(wrong_magic))

    wrong_major = bytearray(frame)
    wrong_major[4] = 2
    with pytest.raises(ProtocolError, match="major"):
        decode_frame(bytes(wrong_major))

    unknown_flags = bytearray(frame)
    unknown_flags[8:10] = struct.pack("!H", 1 << 10)
    with pytest.raises(ProtocolError, match="flags"):
        decode_frame(bytes(unknown_flags))

    with pytest.raises(ProtocolError, match="length"):
        decode_frame(bytes(frame) + b"extra")


def test_payload_size_and_json_safety_are_enforced():
    envelope = Envelope(MessageType.WORLD_UPDATE, 1, {"changes": "x" * 20})
    with pytest.raises(ProtocolError, match="exceeds"):
        encode_frame(envelope, max_payload=10)
    with pytest.raises(ProtocolError, match="valid JSON"):
        encode_frame(Envelope(MessageType.WORLD_UPDATE, 1, {"changes": float("nan")}))


def test_required_fields_and_batch_items_are_validated():
    with pytest.raises(ValueError, match="instance_id"):
        make_envelope(MessageType.COMMAND_BATCH, 1, {"commands": []})
    with pytest.raises(ValueError, match="containing kind"):
        make_envelope(
            MessageType.COMMAND_BATCH,
            1,
            {"instance_id": "x", "commands": [{"value": 0.5}]},
        )


def test_sequence_tracker_detects_gaps_and_duplicates():
    tracker = SequenceTracker()
    tracker.accept(7)
    tracker.accept(8)
    with pytest.raises(ProtocolError, match="expected 9"):
        tracker.accept(10)

    duplicate = SequenceTracker()
    duplicate.accept(1)
    with pytest.raises(ProtocolError, match="expected 2"):
        duplicate.accept(1)


def test_version_negotiation_chooses_highest_shared_minor():
    assert negotiate_version(
        ProtocolVersion(1, 0),
        ProtocolVersion(1, 4),
        local_min=ProtocolVersion(1, 1),
        local_max=ProtocolVersion(1, 2),
    ) == ProtocolVersion(1, 2)
    with pytest.raises(ValueError, match="major"):
        negotiate_version(ProtocolVersion(2, 0), ProtocolVersion(2, 1))


def test_hello_builder_is_a_valid_negotiation_payload():
    payload = hello_payload(
        role="plugin",
        build={"name": "LogicProGym Bridge", "format": "AU", "version": "0.1.0"},
    )
    envelope = make_envelope(MessageType.HELLO, 0, payload)
    assert decode_frame(encode_frame(envelope)).payload["role"] == "plugin"


def test_world_commands_and_event_provenance_are_wire_serializable():
    world = MusicWorldDescription(
        "lab",
        "Music Lab",
        tracks=(TrackDescriptor("synth", "Synth"),),
        controls=(ControlDescriptor("synth/cutoff", "synth", "Cutoff"),),
    )
    description = make_envelope(
        MessageType.WORLD_DESCRIPTION,
        3,
        {"world": world_payload(world)},
    )
    assert decode_frame(encode_frame(description)).payload["world"]["controls"][0][
        "access"
    ] == "shared"

    command = DawCommand(
        "synth",
        "world.control.set",
        {"control_id": "synth/cutoff", "value": 0.5},
        timestamp_samples=2048,
        command_id="command-1",
    )
    event = DawEvent(
        2048,
        "synth",
        EventSource.AGENT,
        "parameter",
        {"parameter_id": "synth/cutoff", "value": 0.5},
        command_id="command-1",
    )
    assert command_payload(command)["command_id"] == event_payload(event)["command_id"]
    assert event_payload(event)["source"] == "agent"
