# Write your own session YAML

To use scanned parameter names, see [catalog references and generated Mackie actions](mackie-discovery.md#reference-the-catalog-in-yaml).

YAML describes **what the environment exposes**, not how an agent chooses its
actions. Start with a small configuration, preview it, then add controls.
This guide covers the Logic adapters in version 1.0. For complete musical
scenarios, see the [example walkthroughs](../examples/README.md).

## 1. YAML basics

- Use spaces, not tabs; indent nested fields consistently (two spaces below).
- `key: value` defines a setting; a leading `-` creates a list item.
- `[notes, velocity]` is a list; `[1]` is a one-element shape, not a scalar.
- `#` starts a comment. Quote device names, especially names containing punctuation.
- Use `true` and `false` for booleans. Do not repeat a key: duplicate sections
  can silently replace earlier settings. Merge audio, frames, and resets under
  the same `environment:` heading.

Save personal files as `configs/my_*.yaml` (Git-ignored). Keep the public examples
unchanged. YAML does not create tracks, load instruments, assign CCs, or configure
input routing inside Logic. Complete those steps separately.

## 2. The three main sections

| Section | Purpose |
| --- | --- |
| `adapter` | Transport: MIDI ports and/or Mackie assignments |
| `tracks` | Named roles, requested observations, and agent actions |
| `environment` | Optional capacities, timing, audio, frames, and reset baselines |

`alias` is your role name, such as `human` or `synth`; it is not the Logic track
name. Match it exactly in MIDI `track_id` and Mackie controller `id` fields.
Mackie `track` is a separate one-based position in the current eight-track bank.

## 3. Start with notes only

Save this complete configuration as `configs/my_notes.yaml`. Replace the output
placeholder with an exact name from `logicprogym devices` and route that bus to
your chosen instrument in Logic.

```yaml
adapter:
  type: logic_midi
  routes:
    - track_id: agent
      output_port: "YOUR_AGENT_OUTPUT"
      channel: 0  # Wire MIDI channel 1; YAML uses 0..15.
tracks:
  - alias: agent
    actions:
      preset: notes_only
```

```bash
logicprogym devices
logicprogym preview configs/my_notes.yaml
logicprogym doctor configs/my_notes.yaml
```

Preview constructs spaces without opening devices. Doctor without `--live`
checks setup but cannot prove routing inside Logic. Add `--live` for connection
checks, including configured Mackie parameters where applicable.

The preset creates two action dictionary keys:

- `agent/note_gate`: 128 binary values, one per MIDI pitch. A rising gate starts
  a note; a falling gate releases it; an unchanged gate does not retrigger it.
- `agent/velocity`: 128 float values in 0..1, used when notes start. Changing
  velocity alone does not change an already-held note.

Every step must provide every configured action key. Adding an action therefore
also changes what your policy must output. A generic example may not accept a
different action schema; check its walkthrough before modifying its YAML.

## 4. Add human input and a custom knob

This complete session observes the keyboard and lets the agent play notes and
control CC20. Replace both port placeholders. First map CC20 to the intended
plug-in knob using the [assignment guide](control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi).
CC20 does not mean Cutoff unless you make that assignment.

```yaml
adapter:
  type: logic_midi
  routes:
    - track_id: human
      input_port: "YOUR_KEYBOARD_INPUT"
      input_source: human
    - track_id: agent
      output_port: "YOUR_AGENT_OUTPUT"
      channel: 0
tracks:
  - alias: human
    observe: [notes, velocity, controls]
  - alias: agent
    actions:
      preset: notes_only
      add:
        - id: cutoff
          target: midi.cc.20
          representation: continuous
          shape: [1]
          range: [0.0, 1.0]
```

The new action key is `agent/cutoff`; write only `cutoff` as its YAML `id` because
the alias prefix is added automatically. Values are normalized: 0..1 is encoded
as MIDI 0..127. This is a requested CC value, not measured plug-in state.

To control **only knobs**, omit the preset and write `actions` as a list of custom
actions. To allow **no agent actions** on a role, omit `actions` entirely.
Configuring an output port alone does not enable note actions.

## 5. Offer discrete choices instead

This complete knob-only session gives the policy three choices. The policy emits
an index 0, 1, or 2; the corresponding semantic value is sent as a normalized CC.

```yaml
adapter:
  type: logic_midi
  routes:
    - track_id: agent
      output_port: "YOUR_AGENT_OUTPUT"
      channel: 0
tracks:
  - alias: agent
    actions:
      - id: cutoff
        target: midi.cc.20
        representation: discrete
        values: [0.25, 0.5, 0.75]
```

Do not put wire values like `[32, 64, 96]` here: the MIDI CC adapter expects
normalized values. Continuous policy values are still quantized on MIDI output.

## 6. Combine MIDI and Mackie

With `logic_hybrid`, nest transport settings under `adapter.midi` and
`adapter.mackie`. This complete example plays notes and controls Alchemy's
8-Bit Memories Cutoff, assumed to be page 1, slot 2. Verify that mapping locally.

```yaml
adapter:
  type: logic_hybrid
  midi:
    routes:
      - track_id: synth
        output_port: "YOUR_AGENT_OUTPUT"
        channel: 0
  mackie:
    controller_count: 2
    relative_deadzone: 0.1
    max_steps_per_action: 4
    controllers:
      - id: synth
        controller: 2
        track: 2
        parameters:
          - {id: synth/page_1/slot_2, name: Cutoff}
tracks:
  - alias: synth
    observe: [plugin_parameters]
    actions:
      preset: notes_only
      add:
        - id: parameter_vector
          target: plugin.relative_vector
          representation: continuous
          shape: [1]
          range: [-1.0, 1.0]
          encoding:
            parameters:
              - {id: synth/page_1/slot_2, page: 1, slot: 2}
```

Here `synth/parameter_vector` requests relative movement, not a knob position.
Magnitude at or below the deadzone sends nothing; larger values become signed
ticks using `max_steps_per_action`. For two knobs, add a second binding and
change `shape` to `[2]`. Declare both parameter names under the controller.

For Mackie-only control use `type: logic_mackie`, put the Mackie settings directly
under `adapter`, and expose only plugin actions. For MIDI-only control, put
`routes` directly under `adapter` as above. Do not mix these nesting styles.
See [Mackie setup](logic-setup.md) and [feedback validity](parameter-observations.md).

## Field reference

### MIDI transport

Under `adapter` for `logic_midi`, or `adapter.midi` for `logic_hybrid`:

| Field | Meaning / default |
| --- | --- |
| `routes` | List of routes; use matching `track_id` values |
| `routes[].track_id` | Role alias; always specify it explicitly |
| `routes[].name` | Optional descriptive name; defaults to the route ID |
| `routes[].input_port` | Exact MIDI input name; omit if not observing MIDI |
| `routes[].output_port` | Exact output name; required for MIDI actions |
| `routes[].channel` | Output channel 0..15; default 0. Does not filter incoming channels |
| `routes[].input_source` | Event provenance: `human` (default), `agent`, or `daw` |
| `sample_rate` | Default 44100; scales local MIDI timestamps, not Logic's audio rate |

Avoid routing the same physical input to several aliases unless duplicated
observations are intentional. YAML routes do not isolate input destinations in
Logic; configure that routing before a multi-track experiment.

### Mackie transport

Under `adapter` for `logic_mackie`, or `adapter.mackie` for `logic_hybrid`:

| Field | Meaning / default |
| --- | --- |
| `controller_count` | Virtual controller pairs; default 1 |
| `controllers` | Role-to-controller assignments |
| `controllers[].id` | Role alias; specify explicitly |
| `controllers[].controller` | One-based preferred controller; specify explicitly |
| `controllers[].track` | Required position 1..8 in the current Mackie bank |
| `controllers[].parameters` | List of parameter descriptors |
| `parameters[].id`, `name` | Stable parameter ID and expected LCD name |
| `parameters[].page`, `slot` | Optional explicit address; otherwise inferred from `/page_N/slot_N` ID suffix |
| `parameters[].minimum`, `maximum` | Descriptor bounds, defaults 0 and 1; not discovered limits |
| `inter_message_delay` | Seconds between control messages; default 0.1 |
| `relative_deadzone` | Vector values at or below this magnitude send nothing; default 0.1 |
| `max_steps_per_action` | Relative-vector tick scale; default 8 |
| `restore_logic_track` | Optional track-selection restoration after control; not parameter reset |

A single controller uses unnumbered To/From endpoints; two or more use numbered
names. Match the actual virtual endpoints in Logic. Independent simultaneous
Mackie controller operation remains experimental.

### Tracks and observations

| Field | Meaning |
| --- | --- |
| `alias` | Required unique role name, matched to transport IDs |
| `observe` | Selected track signals: `notes`, `velocity`, `controls`, `plugin_parameters`, `transport`; omitted/empty means none |
| `actions` | Omit for no actions; use a list, or `preset` plus optional `add` |
| `match` | Parsed extension metadata; not used by the current Logic factory to resolve tracks |

**Observation selection:** each track exposes only signals listed in `observe`.
Omitting it or using `observe: []` excludes that track's musical state, without
disabling its actions. Shapes and slot indices remain fixed; excluded values
are zeroed and their masks are cleared. Selection applies on reset and every
step, before event history and frame processing, and to `info["snapshot"]` and
snapshot-based rewards as well as numerical observations.

- `notes`: note-on/off events and held-note activity. Without `velocity`, onset
  velocities are zeroed but held-note activity remains correct.
- `velocity`: onset velocity; requires `notes` in the same list.
- `controls`: MIDI CC and pitch-bend events, independently of notes.
- `plugin_parameters`: values/validity and parameter readings owned by that
  track according to discovered descriptors, not parameter-ID prefixes.
- `transport`: session-wide transport state; requesting it on any track enables
  the global transport vector. Otherwise it contains neutral defaults, not live
  transport. Local event timestamps and operational timing remain available.

Unknown names or non-list `observe` values fail before device connection.
Unselected tracks and parameters keep their slot indices but have zero masks.
Raw cached Mackie LCD/page diagnostics and arbitrary backend diagnostics are
omitted from selected snapshots because they may contain unrelated state;
selected `parameter_readings` and operational clock/queue diagnostics remain.
Queue-drop counters are session-wide safety information, not per-track counts.

Audio is separately enabled through `environment.audio` and remains a mixed
signal; MIDI/parameter filtering cannot remove a track's sound from that mix.
This is a policy-facing data contract, not a security sandbox: Python callers
can still access their backend directly. Direct `LogicProEnv(...)` construction
without `track_observations` retains unfiltered behavior for compatibility;
YAML construction always enforces selection. Pass an explicit mapping to opt
into filtering with the low-level constructor.

### Action presets and custom fields

The YAML preset names are `notes_only` and `expressive_instrument`. The latter
adds `pitch_bend` (-1..1), `expression` (CC11, 0..1), and `sustain` (CC64, 0..1)
to note gates and velocity. Pitch-bend range in semitones is set in the instrument.
`add` appends controls; it does not override a preset action. Avoid duplicate IDs.

| Custom action field | Meaning / default |
| --- | --- |
| `id` | Required local name; becomes `alias/id` |
| `target` | Required supported transport target, below |
| `representation` | Required: `continuous`, `discrete`, `binary`, `trigger`, or `multi_discrete` |
| `shape` | Default `[1]`; tensor shape for continuous/binary/trigger actions |
| `range` | Default `[0, 1]`; continuous lower/upper bounds |
| `values` | Required nonempty list for `discrete`; policy chooses an index |
| `dimensions` | Required lists of choices for `multi_discrete`; one index per list |
| `encoding` | Target-specific bindings, such as Mackie page/slot or note-gate pitches |
| `update_mode` | `absolute` (default), `relative`, `hold`, or `trigger`; metadata, not a universal behavioral switch |
| `smoothing_ms` | Default 0; stored in the schema, not implemented as Logic-side smoothing |
| `metadata` | Optional descriptive mapping; does not add transport behavior |

Continuous actions use Gymnasium Box spaces; discrete actions use Discrete;
binary/trigger actions use MultiBinary; multi-discrete actions use MultiDiscrete.
Not every representation works with every target: scalar CCs need scalar
semantic values, and note gates need binary vectors. In particular, keep
companion note velocity continuous; discrete indices are not resolved by the
note-gate velocity path. `trigger` does not automatically implement rising-edge
behavior for arbitrary targets.

### Supported Logic targets

| Target | Practical use |
| --- | --- |
| `midi.note_gate` | Binary held-note vector; use the preset, or `encoding.pitches` matching its length |
| `midi.velocity` | Continuous companion onset velocity for a note gate; not a standalone MIDI message |
| `midi.pitch_bend` | One normalized value -1..1 |
| `midi.cc.N` | One normalized value 0..1; N is 0..127, with 120..127 reserved for channel-mode messages |
| `plugin.relative_vector` | Continuous vector, normally -1..1, with `encoding.parameters` address list |
| `plugin.relative` | One direct signed tick count; `encoding` contains `id`, `page`, `slot`; discrete integer `values` are useful |

Low-level note-on/off and all-notes/all-sound-off command targets exist, but
generic custom-action YAML does not provide the note/velocity payload required
for direct note-on/off messages. Use note gates rather than those low-level
targets. Do not use panic/channel-mode messages as exploratory knob controls.
Backend-neutral Python targets such as `musical.pitch` or `world.control.set`
are not supported by the public Logic YAML adapter. Arbitrary target names do
not create new capabilities. A continuous range alone does not add interpolation
or change the resolution of MIDI.

### Environment options

All are optional, under a single `environment` mapping:

| Field | Default / purpose |
| --- | --- |
| `event_capacity` | 128 event rows |
| `max_tracks` | 16 fixed track slots |
| `max_parameters` | 256 fixed parameter slots |
| `timing` | `false`; adds step-timing diagnostics |
| `frames.enabled` | `false`; opt into fixed local-time observation intervals |
| `frames.duration_seconds` | 0.05 when enabled; supported range 0.01..1 second |
| `audio` | Omitted: no capture; source-specific options below |
| `reset_controls` | Omitted: no configured control baseline restoration |

Capacities size arrays, not actual Logic tracks or instruments. For an
observation-only session, enable frames and omit all actions: the environment
exposes `Discrete(1)` and `step(0)` as a no-op. See [frame observations](frame-observations.md).

For native audio, `audio.source: native`, `bundle_id: auto`, `channels: 2`, and
`window_frames: 4800` are typical. `sample_rate` may be omitted for automatic
detection except in frame mode. Optional `helper_path` and `build_dir` select
the helper or build location. For device capture, set `source: device` and an
explicit `device` name/index; defaults are 48000 Hz, 2 channels, and 4800 frames.
`audio.enabled` defaults to true when the section is present. Native capture
requires permission; frame audio requires an explicit matching sample rate.
See the [audio guide](audio-input.md) for working examples and limitations.

Reset controls use `enabled: true` and a `controls` list whose entries contain
`action` (fully qualified ID), `ownership: agent`, and `value`. Only explicitly
agent-owned absolute CC0..119 and pitch bend are supported. This sends configured
baselines, not captured initial knob positions; see [reset examples](reset-controls.md).

## What belongs in Python, not session YAML?

- Policies and reward functions. The default reward is zero; use a reward
  callback/wrapper or compute intrinsic rewards in your learner.
- Episode length: pass `max_episode_steps` to `gym.make`, or use an example's
  `--steps`/`--episodes` option. There is no general YAML `steps` setting.
- Training/checkpoint options, unless a particular example documents otherwise.
  The top-level `feedback` section is specific to `logic_human_feedback.py`,
  not a general environment feature. Its channel is 1..16, unlike MIDI route
  channels; see the [feedback walkthrough](human-midi-feedback.md).

## Before running a custom policy

1. Discover exact device names and configure routing in Logic.
2. Preview the YAML and inspect the action keys and shapes.
3. Run doctor; for Mackie, scan and verify preset-specific page/slot/name bindings.
4. Start with low volume, a saved project, and a short run. Check which track
   actually receives each action; a printed request is not confirmation.

Unknown fields are not consistently rejected across all sections. A typo may
be ignored rather than produce an error, so use the documented names and
inspect preview output. Frame options are checked more strictly. Do not assume
that a YAML file loading successfully means every instrument mapping works.
