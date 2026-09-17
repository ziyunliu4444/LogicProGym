# Reconnecting control surfaces and audio

Use this guide when virtual endpoints change or Logic displays stale control-surface
state. It is not necessary to delete all controller assignments.

## Mackie endpoints

1. Stop agents and other programs using the same endpoints.
2. Restart Logic Pro to refresh its MIDI/control-surface state.
3. Start a LogicProGym session configured for Mackie so its virtual ports exist.
4. In Logic's Control Surfaces Setup, match each device to the corresponding pair.

| Controller | Logic input | Logic output |
| --- | --- | --- |
| 1 | LogicProGym Control 1 To Logic | LogicProGym Control 1 From Logic |
| 2 | LogicProGym Control 2 To Logic | LogicProGym Control 2 From Logic |

Single-controller configurations may use the unnumbered names
`LogicProGym Control To Logic` and `LogicProGym Control From Logic`.
Use the exact names created by your session. These are bridge endpoints, not
your keyboard or agent note-output bus. Independent multi-controller operation
is experimental.

Stop the session before running doctor or a scanner on the same endpoints.
Run `logicprogym doctor CONFIG.yaml --live` with your configured session file.
This command may select the configured track and navigate Instrument views.
If it fails, inspect the reported display and verify the device pairing and
instrument mapping; do not change parameter names simply to suppress an error.

## Audio helper

Native audio uses the bundled LogicProGym Audio helper. A rebuild or application
identity change may require recording permission again. Follow the
[audio setup guide](audio-input.md); do not grant unrelated permissions.

## Saved sessions

Keep a copy of your Logic project and YAML before changing routes or presets.
Checkpoint resume validates the session configuration but does not restore
Logic state. See [checkpoint guidance](checkpoints-and-release.md).
