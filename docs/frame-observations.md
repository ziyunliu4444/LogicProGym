# Frame-wise observations (opt-in)

Frame mode groups observations into fixed local-time intervals while Logic keeps
running. Existing sessions are unchanged unless you enable it:

```yaml
environment:
  frames:
    enabled: true
    duration_seconds: 0.05
```

Durations from 10 ms to 1 second are supported. One step sends its action once,
waits for the next eligible boundary, and observes the completed interval.
Held notes remain held; relative knob commands are not repeated. This is not
an independent background observation API. To observe without acting, use a
configuration with no agent actions. It exposes `Discrete(1)` and uses
`step(0)` as a no-op, because Gymnasium does not allow empty Dict action spaces.

## Observation-only example

### Prepare Logic

Follow the [installation guide](logic-setup.md#1-install-logicprogym), activate
the virtual environment, and run commands from the source checkout. Open one
instrument track in Logic, route your keyboard to it, and confirm it plays.
No agent track, IAC output bus, or Mackie controller is needed. This is an
observation example, not a learning policy; it saves no checkpoint or recording.

### Configure

```bash
logicprogym devices
cp configs/examples/logic_frames.yaml configs/my_frames.yaml
```

Replace `YOUR_KEYBOARD_INPUT` with the exact physical keyboard input name.
The [annotated YAML](../configs/examples/logic_frames.yaml) has only a human
observation role and enables 0.05-second frames (20 per second). Input events
come directly from the keyboard, not all edits inside Logic.

```bash
logicprogym preview configs/my_frames.yaml
logicprogym doctor configs/my_frames.yaml
```

### Run and inspect

Play and release notes while running:

```bash
python examples/logic_frame_observer.py configs/my_frames.yaml --frames 1200
```

This lasts approximately one minute at 50 ms per frame. Ctrl-C closes the
environment. The script rejects configurations with agent actions and does
not send notes, pedals, mode buttons or knob controls.

To include audio, uncomment the audio section in your copied template and set
`sample_rate` to Logic's actual rate. Native recording permission is required.
The rate must be explicit in frame mode; automatic rate selection is disabled.
Audio shape is `(sample_rate * duration_seconds, channels)`; the sample count
must be an integer. The usual rolling `window_frames` is overridden.

### Expected output and troubleshooting

Each printed dictionary is frame metadata, not a list of note pitches. `index`
should advance; `midi_events` should increase in frames containing incoming
events and can legitimately be zero while a note is held. The full observation
is available inside the script for your own policy or analysis.

- `skipped_frames: 0` and `midi_state_valid: True` indicate no reported frame
  skipping or MIDI state loss; they do not prove sample-accurate DAW alignment.
- `lateness_seconds` reports scheduler delay, not musical tempo.
- With audio enabled, inspect `missing_samples`, `overlap_samples`, and gap
  diagnostics. Missing samples at startup can occur; persistent gaps need
  investigation before using the waveform for training.
- `synchronized_to_logic: False` is expected: this is a local observation clock.
- No MIDI events while pressing keys: check the input name. No audio: first run
  the [audio capture check](audio-input.md#native-logic-capture-no-blackhole).

### Stop

The run exits after the requested number of frames. Ctrl-C closes early.
Because this configuration has no actions, it does not alter instrument controls.

## What a frame contains

- MIDI events received within the local half-open interval [start, end).
  Event rows do not persist into later frames. Future receipts wait for the
  next frame. Held-note state persists and incorporates skipped-interval events.
- A fixed-size audio array with `audio_valid`. Missing samples are zero-filled
  and invalid. Consecutive packets use a **continuous sample-count timeline**,
  anchored to the first packet's arrival. Packet bursts do not independently
  reposition samples. Reset or a reported capture gap restarts the timeline.
  This is not Logic's sample clock: startup latency, late delivery and clock
  drift can still produce missing samples at frame boundaries. No missing
  samples are invented, repeated or marked valid.
- Latest available transport/parameter state. These are NOT reconstructed at
  the exact boundary. Continue checking Mackie age and validity diagnostics.

`info["frame"]` reports index, local start/end, skipped frames, scheduler
lateness, event truncation, receipt-timestamp omissions and MIDI queue drops.
`midi_state_valid` becomes false after a queue loss or un-timestamped event
and stays false until reset. Event-capacity truncation is separately reported.
MIDI queues and deferred events are bounded; audio retains at most two seconds.
`info["audio"]` additionally reports missing/overlapping samples, discarded
buffer samples and gap notifications. Reset returns an initial snapshot, not
a completed frame; audio starts invalid.

## Late callers and limitations

If inference or a scheduler stalls, old frames are skipped, not replayed.
A late step still sends its action only once. Older MIDI events update note
state but are not reported as current-frame events. Data lost to buffer overflow
cannot be recovered. Reset restarts frame numbering and clears deferred events.

Receipt times are not hardware event times. These frames do not guarantee
sample-accurate synchronization, fresh action-caused feedback, or deadline
execution. A reward receives current-frame events and latest parameter state;
audio-aware rewards belong outside the audio wrapper. Frame mode does not
modify your reward automatically.

Before relying on it, live-test MIDI event counts, audio gap masks, Ctrl-C,
and deliberately delayed steps. Automated tests do not certify hardware timing.
