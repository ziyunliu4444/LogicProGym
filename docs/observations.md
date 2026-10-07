# Using observations

LogicProGym returns a dictionary of fixed-shape NumPy arrays from `reset()` and
`step(action)`. Your policy can use held notes, recent MIDI events, available
instrument-parameter readings, and optional raw audio. What is available depends
on your routing, adapter, and YAML configuration.

## Select what the agent observes

This fragment goes in an existing session YAML with configured adapter routes
and parameter controls:

```yaml
environment:
  event_capacity: 128
  max_tracks: 3
  max_parameters: 16

tracks:
  - alias: human
    observe: [notes, velocity, controls]
  - alias: agent
    observe: [plugin_parameters]
    # Keep your configured actions here.
```

Aliases must match the adapter's track IDs. `notes` exposes held-note activity
and note events; `velocity` adds onset velocity and requires `notes`. `controls`
exposes MIDI CC and pitch-bend events. `plugin_parameters` exposes selected
parameters belonging to that track. Add `transport` to any track to request the
session-wide transport vector.

Omitting `observe`, or setting it to `[]`, hides that track's musical state;
its configured actions still work. Selection applies to numerical observations
and `info["snapshot"]`. Audio is configured separately and contains the captured
mix. See the [YAML reference](yaml-configuration.md#tracks-and-observations).

## Fields and masks

Here, `T = max_tracks`, `P = max_parameters`, `E = event_capacity`,
`W = audio.window_frames`, and `C` is the capture channel count (2 for native
Logic capture). Core fields remain present even when a signal is not selected;
the audio fields are added when `environment.audio` is enabled.

| Field | Shape / dtype | Meaning |
| --- | --- | --- |
| `active_notes` | `(T, 128, 3)` / float32 | For each track and MIDI note: active flag, onset velocity, source code |
| `track_mask` | `(T,)` / int8 | Discovered tracks with selected observation fields |
| `events` | `(E, 8)` / float64 | Recent event rows; layout below |
| `event_mask` | `(E,)` / int8 | Rows containing events rather than padding |
| `parameter_values` | `(P,)` / float32 | Accepted numeric parameter readings |
| `parameter_mask` | `(P,)` / int8 | Discovered, selected parameters |
| `parameter_valid` | `(P,)` / int8 | Parameters with an available numeric reading |
| `transport` | `(5,)` / float64 | Sample position, sample rate, tempo, beat position, playing flag |
| `audio` | `(W, C)` / float32 | Raw captured audio waveform, clipped to −1–1; native capture reads Logic's mixed stereo output |
| `audio_valid` | `(W,)` / int8 | Frames with available captured samples; distinguishes silence from missing audio |

Arrays use zero padding. A zero parameter value can be a real reading or an
unavailable reading: check `parameter_valid`. `track_mask` and `parameter_mask`
describe selection and registration, not freshness. Transport contains neutral
defaults when not selected; actual transport support depends on the adapter.

Track and parameter slots are zero-based registry indices, **not Logic track
numbers or MIDI channels**. Resolve IDs after `reset()`:

```python
import logicprogym

env = logicprogym.make("configs/my_session.yaml")
try:
    observation, info = env.reset()
    registry = env.unwrapped.registry
    for slot, track in enumerate(registry.tracks):
        print(slot, track.id, track.name)
    for slot, parameter in enumerate(registry.parameters):
        print(slot, parameter.id, parameter.name)
    # Use the same observation fields returned by env.step(action).
finally:
    env.close()
```

The snippets below operate on an `observation` and `info` returned by that
environment. Replace the example IDs with IDs in your configuration.

## Read held notes

```python
import numpy as np

human_slot = registry.track_slot("human")
if observation["track_mask"][human_slot]:
    notes = observation["active_notes"][human_slot]
    pitches = np.flatnonzero(notes[:, 0] > 0)
    velocities = notes[pitches, 1]
    sources = notes[pitches, 2].astype(int)
    print("Held MIDI pitches:", pitches, "velocities:", velocities)
```

Onset velocities are normalized to 0–1. If `velocity` is not selected, that
column is zero while activity is retained. Source codes are human `0`, agent
`1`, DAW `2`; interpret the source only for active notes. This state reflects
received MIDI messages, not audio pitch detection or a reconstruction of every
note already sounding in Logic before connection/reset.

## Read events and MIDI controls

Each valid row in `events` has these eight columns:

```text
[timestamp_samples, track_slot, source_code, kind_code,
 primary, secondary, has_command_id, reserved_zero]
```

| Kind code | Event | Primary | Secondary |
| --- | --- | --- | --- |
| 0 | Note on | MIDI note | Normalized velocity |
| 1 | Note off | MIDI note | Normalized release velocity |
| 2 | Pitch bend | Adapter's pitch value | 0 |
| 3 | MIDI control | CC number | Normalized value |
| 4 | Parameter | Parameter registry slot | Numeric value |
| 5 | Transport | Event's value | 0 |

The final column is reserved; it is not a MIDI channel. `has_command_id` is a
flag, not the command identifier itself.

```python
from logicprogym.observations import EVENT_KIND_CODES

rows = observation["events"][observation["event_mask"].astype(bool)]
human_controls = rows[
    (rows[:, 1] == human_slot)
    & (rows[:, 3] == EVENT_KIND_CODES["control"])
]
for row in human_controls:
    print("CC", int(row[4]), "value", row[5])
```

In ordinary mode, these rows are a rolling history of the newest `E` events.
The same event can appear on several steps. Do not count every row on every
step as a new keyboard rating or note onset. For newly received events in the
current snapshot, use the structured objects:

```python
for event in info["snapshot"].events:
    if event.track_id == "human" and event.kind == "note_on":
        print(event.values["note"], event.values["velocity"])
        # MIDI adapter events also carry a zero-based channel when available.
        channel = event.values.get("channel")
```

Structured events expose `track_id`, `source`, `kind`, `timestamp_samples`,
`values`, and `command_id`. Local MIDI timestamps are estimates based on a
local clock, not sample-accurate Logic timeline positions. For interval-specific
events and MIDI/audio windows, see [frame observations](frame-observations.md).

## Read instrument parameters

```python
parameter_slot = registry.parameter_slot("agent/page_1/slot_2")
if (observation["parameter_mask"][parameter_slot]
        and observation["parameter_valid"][parameter_slot]):
    cutoff = float(observation["parameter_values"][parameter_slot])
    print("Reported Cutoff:", cutoff)
else:
    print("Cutoff reading unavailable")
```

Mackie readings are asynchronous display feedback. Percentages become 0–1;
bare numeric readings retain their displayed units. Text labels and fractions
such as `1/16` are not available as numeric values. A valid reading does not
acknowledge an action or prove that the action moved a knob.

For raw text and numeric feedback, use the public interface. It works for
Mackie-only and hybrid environments without backend-specific dictionary access:

```python
readings = logicprogym.parameter_readings(info)
cutoff = readings.get("agent/page_1/slot_2")
if cutoff is not None:
    print(cutoff.name, cutoff.raw, cutoff.age_seconds)
    if cutoff.valid:
        print("Accepted numeric value:", cutoff.value)
```

Each immutable `ParameterReading` has `id`, `name`, `raw`, `age_seconds`,
`value`, and `valid`. `raw` is the last received display text, including labels
and fractions, or `None` if unavailable. Its age can be `None` when no receipt
information is available. Historical raw text does not establish numeric
validity; `value` is `None` unless `valid` is true. The function only reads the
supplied reset/step result: it does not poll devices or produce additional steps.
Only selected parameter feedback is returned; absent feedback yields `{}`.

See [parameter observations](parameter-observations.md) for matching, expiry,
and setup requirements. Raw cached LCD text is not a substitute for a valid
parameter observation.

## Observe raw audio

LogicProGym can capture Logic Pro's output directly through native macOS audio
capture. Keep Logic's normal audio output device and add this to your existing
session's `environment` mapping:

```yaml
environment:
  audio:
    source: native
    bundle_id: auto
    window_frames: 4800
```

This adds `audio` with shape `(4800, 2)` and dtype float32, and `audio_valid`
with shape `(4800,)` and dtype int8. Samples are clipped to −1–1. The validity
mask distinguishes captured silence from missing samples. The capture is stereo;
the sample rate is detected from Logic and returned in `info["audio"]["sample_rate"]`.
At 48000 Hz this window spans 100 ms; at 44100 Hz it spans about 109 ms.

Native capture requires macOS 14.2 or later, Apple's Xcode Command Line Tools
to build the bundled helper on first use, and system-audio recording permission.
With Logic open and producing sound, check capture with:

```bash
python live_tests/logic_audio_test.py --source native --seconds 30
```

See [native audio setup](audio-input.md#native-logic-capture-no-blackhole) for
permissions and troubleshooting. `bundle_id: auto` selects the running Logic
edition. Capture reads Logic's mixed output, including its instruments and
effects; it does not require a virtual audio device.

Both `logicprogym.make()` and Gymnasium's registered environment attach audio
capture from this YAML. Capture opens on `reset()`. Read the waveform directly
from the observation returned by each `step(action)`:

```python
observation, reward, terminated, truncated, info = env.step(action)
valid = observation["audio_valid"].astype(bool)
if valid.any():
    waveform = observation["audio"][valid]
    rms = float(np.sqrt(np.mean(np.square(waveform, dtype=np.float64))))
    sample_rate = info["audio"]["sample_rate"]
    print("Audio RMS:", rms, "sample rate:", sample_rate)
else:
    print("No valid audio samples yet")
```

Ordinary audio windows place the newest samples at the end. They can overlap,
repeat, and include sound from before the last action; `info["audio"]` supplies
sequence, age, sample rate, and capture-status information. Reset clears the
window, so initial samples may be unavailable. Audio is a captured mix, not a
separate waveform for each MIDI track. Pitch, spectra, embeddings, and other
features must be computed by your code.

Audio does not need an `audio` entry in a track's `observe` list:
`environment.audio` enables it for the whole environment. An audio-only policy
can leave track observation lists empty and use `observation["audio"]` and
`observation["audio_valid"]` directly, while retaining whichever actions its
task requires.

## Use observations in a policy or reward

Your policy can select the fields it needs and compute features from them.
LogicProGym supplies observations and control; it does not prescribe a musical
objective or provide a predefined task reward. The default reward is zero.
Define your own reward for your task, either in your training loop or through
the reward interfaces.

For rewards that need raw audio, wrap the configured environment with
`logicprogym.FunctionReward`, which can inspect the audio-augmented observation.
The factory's snapshot reward runs before the audio wrapper. See the
[audio guide](audio-input.md#enable-gymnasium-observations) and
[learning examples](../examples/README.md) for runnable uses.
