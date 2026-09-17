# Opt-in episode initialization

By default, reset does not restore presets or knob positions. To initialize
selected controls on every reset, add this to your session YAML:

```yaml
environment:
  reset_controls:
    enabled: true
    controls:
      - {action: synth/cutoff, ownership: agent, value: [0.5]}
      - {action: synth/pitch_bend, ownership: agent, value: [0.0]}
      - {action: synth/sustain, ownership: agent, value: [0.0]}
```

Each action ID must already exist in the session's action space. For example,
cutoff can be a MIDI CC20 action learned by Logic, pitch_bend a MIDI pitch-bend
action, and sustain a MIDI CC64 action. Omit actions you have not configured.
Continuous values use the action's shape (normally a one-element list).
CC values are normalized to 0..1 and bend to -1..1. Discrete actions use their
policy index, which must resolve to a valid normalized value.

Only absolute MIDI CC0..119 and pitch bend are accepted. Mackie relative
controls, note-on triggers, channel-mode messages, unknown/duplicate actions,
invalid shapes and nonfinite values are rejected before connection.

`ownership: agent` is your explicit declaration that the destination control
is exclusively agent-owned. Human-only and shared ownership are rejected.
The software cannot detect which physical instruments share a MIDI port/channel:
use separate routes from the human track. Never declare a shared pedal or knob
agent-owned merely to bypass the check.

Initialization runs after normal backend reset and before obtaining the initial
observation. It does not advance a Gymnasium step or calculate a reward.
Existing reset cleanup releases locally tracked agent notes; include an explicit
CC64 reset to zero when your agent uses sustain, so released notes do not linger.
It does not silence arbitrary human tracks, reload Logic or seek the transport.

`info["reset_controls"]` reports `status: sent`, the commands and
`confirmed: false`. Sent means the backend call returned, not that Logic
acknowledged the values. The first observation can still reflect asynchronous
feedback. Errors propagate; a failed reset is not successful initialization.
A failed batch can have partially affected Logic—retry only after checking the
connection. There is no transactional rollback.

Disable with `enabled: false` or omit the section for continuous sessions.
The dedicated cutoff-reset template explicitly enables its documented baseline.

## Cutoff reset example

Copy `configs/examples/logic_cutoff_reset.yaml` to `configs/my_cutoff_reset.yaml`
and replace `YOUR_AGENT_OUTPUT` with your MIDI output bus. YAML channel `0`
means channel 1 in Logic. Map CC20 to a fixed agent instrument's Cutoff using
Unsigned / Scaled, incoming range 0..127, then turn Learn Mode off.

```bash
python live_tests/logic_cutoff_reset_test.py configs/my_cutoff_reset.yaml
```

The requests are 50% → 85% → reset to 50% → 15% → reset to 50%.
No notes are sent and no plug-in window is opened. Watch the knob manually;
actual units and response depend on the learned assignment.

Reset restores a **configured baseline**, not an automatically captured knob
position. MIDI CC output does not provide readback. Capturing an arbitrary
initial plug-in state is not implemented.

For held-note, sustain and pitch-bend tests, configure their reset values as
above and run `python live_tests/logic_reset_test.py YOUR_SESSION.yaml`.
Both reset CLIs use the supervisor described in [shutdown](shutdown.md).
