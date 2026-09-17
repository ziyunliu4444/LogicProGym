# LogicProGym Bridge Protocol v1

Status: draft implementation contract

The protocol connects the Python music-world server to bridge-plugin instances
running inside DAWs. Audio threads never read, write, parse, or wait on protocol
frames. Each plugin uses lock-free queues between its audio callback and a
dedicated communication thread.

## 1. Transport

Version 1 uses a reliable ordered byte stream. Implementations should support a
loopback TCP connection; Unix-domain sockets or named pipes may be offered when
both peers support them. The plugin initiates the connection to the Python server.

Connections must bind locally by default. A server exposed beyond loopback must
require authentication and encryption supplied by a later transport profile.

## 2. Binary frame

Every message starts with this 32-byte network-byte-order header:

| Offset | Size | Type | Field |
|---:|---:|---|---|
| 0 | 4 | bytes | Magic `DGYP` |
| 4 | 1 | uint8 | Protocol major |
| 5 | 1 | uint8 | Protocol minor |
| 6 | 2 | uint16 | Message type |
| 8 | 2 | uint16 | Flags |
| 10 | 2 | uint16 | Reserved; must be zero |
| 12 | 4 | uint32 | Payload length in bytes |
| 16 | 8 | uint64 | Sender sequence number |
| 24 | 8 | int64 | DAW sample timestamp, or `-1` |

The payload is UTF-8 JSON in v1. JSON parsing happens only on communication or
control threads. A frame payload must not exceed 1 MiB unless peers negotiate a
different limit in `HELLO`/`WELCOME`.

Sequence numbers are monotonically increasing independently in each direction.
A gap indicates dropped/corrupt application data even though the transport is
reliable. Duplicate or decreasing values are protocol errors.

## 3. Version negotiation

The first plugin frame is `HELLO`. It declares its supported minimum and maximum
versions, plugin build, plugin format, maximum frame size, and optional session
token. The server responds with exactly one of:

- `WELCOME`: negotiated version, session ID, limits, heartbeat interval;
- `REJECT`: machine-readable reason and human-readable message.

Peers must share the same major version. They negotiate the greatest mutually
supported minor version. Unknown optional JSON fields must be ignored. Unknown
message types or required fields are errors.

## 4. Connection lifecycle

```text
Plugin                              Python server
  | -------- HELLO --------------------> |
  | <------- WELCOME ------------------- |
  | -------- REGISTER_INSTANCE --------> |
  | <------- WORLD_DESCRIPTION --------- |
  | <====== EVENT/COMMAND batches =====> |
  | <====== HEARTBEAT =================> |
  | -------- UNREGISTER_INSTANCE ------> |
```

One connection may register multiple plugin instances, but one connection per
instance is also valid. Every instance has a persistent random UUID stored in the
DAW project state. Runtime connection IDs are not stable identities.

## 5. Message types

| Code | Name | Direction | Purpose |
|---:|---|---|---|
| 1 | `HELLO` | plugin → server | Version and transport negotiation |
| 2 | `WELCOME` | server → plugin | Accept connection and select version |
| 3 | `REJECT` | server → plugin | Reject incompatible/unauthorized peer |
| 4 | `HEARTBEAT` | both | Liveness and latest sequence/sample time |
| 10 | `REGISTER_INSTANCE` | plugin → server | Register one track/plugin instance |
| 11 | `UNREGISTER_INSTANCE` | plugin → server | Remove an instance cleanly |
| 12 | `WORLD_DESCRIPTION` | server → plugin/client | Full tracks/devices/controls schema |
| 13 | `WORLD_UPDATE` | both | Incremental discovery/state metadata |
| 20 | `COMMAND_BATCH` | server → plugin | Timestamped agent/world commands |
| 21 | `EVENT_BATCH` | plugin → server | Human, agent echo, DAW and parameter events |
| 22 | `STATE_SNAPSHOT` | both | Current transport/control/note state |
| 30 | `RESET_REQUEST` | server → plugin | Begin a new episode safely |
| 31 | `RESET_ACK` | plugin → server | Reset completed at reported sample time |
| 32 | `ALL_NOTES_OFF` | server → plugin | Urgent defensive silence command |
| 255 | `ERROR` | both | Protocol or command failure |

## 6. Registration and capability discovery

`REGISTER_INSTANCE` includes:

```json
{
  "instance_id": "stable-uuid",
  "runtime_id": "connection-specific-uuid",
  "name": "Agent Synth",
  "plugin": {"name": "LogicProGym Bridge", "format": "AU", "version": "0.1.0"},
  "track_hint": {"name": "Synth", "index": 2},
  "capabilities": ["midi_input", "midi_output", "host_timing", "parameters"],
  "controls": []
}
```

Capabilities are claims, not assumptions. The Python server validates experiment
requirements before starting an episode. Controls use stable IDs, normalized
values where possible, explicit kinds, ranges, access policies, and conflict
policies from the music-world schema.

## 7. Time

Header timestamps and event timestamps use the DAW host sample timeline. `-1`
means the sender has no authoritative sample time. Each transport snapshot includes
sample rate, sample position, tempo, beat position, play state, and loop state.

Commands may specify either:

- `timestamp_samples`: absolute host sample position;
- `sample_offset`: offset inside the next processing block;
- neither: apply as soon as safely possible.

The plugin reports late commands. It must not block the audio callback waiting for
a command. Sample-accurate capability is declared only when commands are scheduled
inside the audio block at the requested offset.

## 8. Events and commands

Events and commands are batched to reduce communication overhead. Each item has a
stable ID, target instance/track/control, kind, values, and source. Agent commands
retain `command_id` when echoed back, allowing the server to distinguish agent
effects from human input.

Supported foundational kinds include:

- `note_on`, `note_off`, `pitch`, `control`;
- `parameter_set`, `parameter_changed`;
- `transport_changed`, `audio_features`;
- `all_notes_off`.

Unknown semantic kinds must be rejected with `ERROR`, not silently ignored.

## 9. Reset and safety

`RESET_REQUEST` contains an episode ID, requested state policy, and optional target
sample. A plugin must stop agent notes, clear queued commands, restore declared
defaults/state, and respond with `RESET_ACK`. The environment cannot return from
`reset()` until all required instances acknowledge or the reset times out.

If heartbeats stop, the connection closes, Python crashes, or a queue overflows,
the plugin must prioritize note-offs and enter its configured fail-safe state.
Audio must continue. Lower-priority audio-feature frames may be dropped; note-off,
reset, and safety messages must not be dropped.

## 10. Backpressure

Implementations use bounded queues with priority classes:

1. reset, all-notes-off, note-off;
2. note-on and discrete events;
3. control/parameter changes;
4. transport snapshots;
5. audio features and diagnostics.

On overflow, discard/coalesce from the lowest class first and report counts in the
next diagnostics or heartbeat payload.

## 11. Errors

`ERROR` contains:

```json
{
  "code": "unsupported_command",
  "message": "Instance cannot set another plugin's parameter",
  "fatal": false,
  "correlation_id": "request-or-command-id",
  "details": {}
}
```

Fatal errors close the connection after the frame is flushed. Nonfatal command
errors leave the session active. Implementations must never silently substitute a
different track or parameter.

## 12. Reproducibility

Recordings store negotiated protocol version, world description, plugin builds,
capabilities, ordered frames, sample timestamps, reset acknowledgements, and any
dropped/coalesced counts. A recording must be replayable without loading its DAW.

