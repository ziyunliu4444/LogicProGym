# Let the agent hear Logic

Optional audio observations give the policy a rolling PCM waveform. On macOS
14.2 or later, native capture can read Logic's application output directly.
Audio-device capture remains available for interface loopback and virtual audio
devices. MIDI ports do not carry audio.

## Native Logic capture (no BlackHole)

Keep Logic's current audio output device. Open Logic and play a sound so its
audio engine is active, then run from the source checkout:

```bash
python live_tests/logic_audio_test.py --source native --seconds 30
```

The first run compiles a small bundled Swift helper using Apple's Xcode Command
Line Tools. If those tools are missing, run `xcode-select --install` and retry.
The helper is cached under `~/Library/Caches/logicprogym/native-audio/`. Native
capture uses macOS directly and needs no separate driver, additional Logic
tracks, or MIDI changes. It leaves Logic's output audible.

### First-run recording permission

**Users must grant macOS system-audio recording permission.** LogicProGym cannot
grant this permission automatically. Allow it when the capture test prompts you.
Permission belongs to the capturing helper or the application launching it;
adding Logic itself is not the setup step.

If permission is denied, open **System Settings > Privacy & Security > Screen
& System Audio Recording**. Enable recording access for the application you
use to run the script, or the capture helper if macOS identifies it in the
permission prompt. Native capture reads application output and does not require
microphone access.

If no entry or prompt appears, run the native test command above first. After
changing permission, stop the test and quit/reopen the launching application if
macOS requests it, then run the test again. Permission is normally remembered
for subsequent runs. Rebuilding/replacing the helper or changing the launching
application may require approval again.

Confirm RMS and peak respond when Logic plays sound; a permission prompt alone
does not establish successful capture. This test sends no MIDI and exits
automatically; Ctrl-C also stops it. Capture does not save recordings to disk.

### Enable native audio for an agent

Add these fields to your existing session's `environment` section to enable the
same source for an agent:

```yaml
environment:
  audio:
    source: native
    bundle_id: auto
    window_frames: 4800
```

The sample rate is detected from Logic's tap and reported in `info['audio']`.
The default `bundle_id: auto` selects the running Logic edition: standard Logic
uses `com.apple.logic10`, while Logic Pro Creator Studio uses
`com.apple.mobilelogic`. If both are running, select one explicitly. If an older
session explicitly contains `com.apple.logic10`, change it to `auto` when using
Creator Studio. A missing application error happens before audio capture and
does not indicate a recording-permission problem.
You may specify `sample_rate` to require a particular rate, but a mismatch raises
an error; native capture does not resample. The window is stereo float32 with
shape `(window_frames, 2)`. It spans 100 ms at 48000 Hz, or about 109 ms at
44100 Hz. This captures the selected application's mixed output, not separate
track stems. Other applications are not included as a fallback. If audio is
rendered through a separate hosting process and is absent from the tap, use the
device route below or explicitly select the intended process.

Useful diagnostics and optional build controls:

```bash
python live_tests/logic_audio_test.py --source native --list
python -m logicprogym.native_audio --build-dir artifacts/native-audio
```

`--list` lists running application names and bundle IDs without capturing.
`--bundle-id` selects another application explicitly. An existing helper can be
selected with `helper_path` in YAML; `build_dir` selects a build cache location.
Wheel installs include the Swift source and permission metadata. They currently
build locally; prebuilt signed/notarized helper distribution is not included.

The helper uses [Apple's Core Audio process taps](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps).
Python receives bounded PCM packets. If it cannot keep up, the helper drops
packets instead of blocking the audio callback; a detected gap clears the old
window and increments the status count. Closing the environment requests native
cleanup, with process termination as a bounded fallback. Parent-process exit
also closes the helper's control pipe. Logic exit or audio-format changes require
restarting capture and are reported as errors.

## Audio-device routing (alternative)

Audio-device support is included in the standard installation:

```bash
python -m pip install -e .
python live_tests/logic_audio_test.py --list
```

On macOS, one option is BlackHole 2ch. Install the driver separately following
[BlackHole's instructions](https://existential.audio/blackhole/support/).
In Audio MIDI Setup, create a Multi-Output Device containing your headphones or
audio interface and BlackHole. Configure drift compensation as instructed by
the driver. Select that Multi-Output Device as Logic's output under
**Logic Pro > Settings > Audio > Devices**. Python captures **BlackHole 2ch** as
its input. This lets you and the policy hear the same stereo mix. Match the
device and project sample rates; the example below uses 48000 Hz.
See the [driver's Logic routing example](https://www.existential.audio/howto/StreamFromLogicProXtoZoom.php).

No extra MIDI tracks or Mackie assignments are required. If macOS requests
audio-input permission for the terminal or IDE, grant it to run capture.
Keep Logic input monitoring of the loopback signal off to avoid feeding the
captured mix back into itself.

## Test reception

```bash
python live_tests/logic_audio_test.py --device "BlackHole 2ch" --seconds 30
```

Play notes or audio in Logic. RMS and peak should rise with sound and fall with
silence. The test exits after 30 seconds; Ctrl-C stops early. It sends no notes,
changes no knobs, and does not record files. Zero valid frames means no recent
audio arrived. Valid frames with zero amplitude can mean silence or incorrect
routing. Rising callback status counts indicate audio delivery problems.

## Enable Gymnasium observations

Add this inside the existing `environment` section of your session YAML:

```yaml
environment:
  audio:
    source: device
    enabled: true
    device: "BlackHole 2ch"
    sample_rate: 48000
    channels: 2
    window_frames: 4800
```

Both `logicprogym.make()` and `gym.make('LogicProGym/Logic-v0', config_path=...)` attach
the audio wrapper when configured. Device opening happens on reset. The normal
observation gains `audio` (float32, 4800 frames by 2 channels here) and
`audio_valid` (one binary value per frame). Samples are clipped to [-1, 1].
Reset clears the window; initial samples may be unavailable. The newest samples
are at the end. `info['audio']` contains sample rate, callback sequence, age and
status count. Use `logicprogym.FunctionReward` around this environment if a custom
reward should inspect audio; the factory's snapshot reward runs before the
audio wrapper and does not see these extra observations.

Audio is asynchronous: windows may overlap, repeat when stepping quickly, and
include sound from before the last action. Sequence numbers help detect reused
windows. This is not sample-aligned action/audio recording. The input contains
whatever mix you route to it; separating human and agent tracks requires separate
audio routing, not inference from MIDI track names. Feature extraction and
curiosity rewards are research choices; the bridge supplies the waveform.

## Example: an agent acts on raw audio

### Prepare Logic

Use the [standard installation](logic-setup.md#1-install-logicprogym) and activate
its virtual environment. Save a copy of your project and lower monitoring volume.
One software-instrument track is enough: load Alchemy, choose a preset with a
Cutoff macro, and play it from your keyboard. The agent sends no notes.

Enable an IAC bus and map its channel-1 CC20 to that specific instrument's Cutoff
using the [MIDI assignment walkthrough](control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi).
Use an explicit target track rather than an unintended Selected Track assignment.
Verify the mapping with the linked CC test, then leave Learn Mode off. No Mackie
controller is needed. Complete the [native capture and permission check](#native-logic-capture-no-blackhole)
above; confirm RMS responds before running the policy.

### Configure

```bash
logicprogym devices
cp configs/examples/logic_audio_agent.yaml configs/my_audio_session.yaml
```

Replace `YOUR_AGENT_OUTPUT` in your copy with the exact IAC output used for the
assignment. The [annotated YAML](../configs/examples/logic_audio_agent.yaml)
contains one `midi.cc.20` action, with normalized range 0..1, MIDI `channel: 0`
(wire channel 1), and native mixed-audio observations. `window_frames: 4800`
is a sample count, not a control-step duration.

```bash
logicprogym preview configs/my_audio_session.yaml
logicprogym doctor configs/my_audio_session.yaml
```

### Run and listen

`logic_audio_agent.py` uses the standard Gymnasium reset/step interface, a
TimeLimit for finite runs, and RecordEpisodeStatistics. Its policy receives
`observation['audio']`, computes RMS energy directly from those waveform samples,
and maps the level onto a learned MIDI CC knob assignment. Louder audio produces
a higher requested CC value; quieter audio produces a lower value. Requests
are smoothed and limited to 15–85% of the CC range. The initial request is 50%.

You play the notes; the policy changes only the configured CC. To hear timbre changes, play the instrument whose Cutoff is
mapped, or arrange for that instrument to receive notes in Logic.

```bash
python examples/logic_audio_agent.py --config configs/my_audio_session.yaml
```

The default run lasts 300 control steps, approximately 30 seconds after setup.
To run until Ctrl-C, or choose a different session:

```bash
python examples/logic_audio_agent.py --config configs/my_audio_session.yaml --steps 0
python examples/logic_audio_agent.py --config configs/my_audio_session.yaml --steps 100
```

### Expected output and troubleshooting

The example configuration requires exactly one scalar MIDI CC action. If your
audio is very quiet, lower the upper reference level, for example `--loud-db -24`.
The default reference range is -60 to -12 dBFS. Logs show measured audio level,
audio availability, and requested CC values. They do not claim a measured knob
percentage. Missing, incomplete or repeated audio holds the previous request.

This is a deterministic audio-conditioned policy, not a trained model. Reward
remains zero and no weights are saved. Replace `AudioEnergyPolicy.act` with your
model to use the same audio/control loop. Native capture hears the Logic mix,
including the controlled instrument, so knob changes can themselves affect the
next audio observation. The bridge does not isolate human audio automatically.

### Stop

The finite run closes automatically; Ctrl-C stops early. Closing shuts down
capture and the MIDI connection. The example does not automatically restore
the knob's initial position; reload your saved preset or restore it manually.
No audio recording or learned checkpoint is saved.

Native capture requires permission and a compatible audio setup. Validate
reception, sample rate, shutdown and reopening on your machine before using
observations for training. See the [live checklist](logic-1.0-acceptance.md).
