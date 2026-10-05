# Checkpoints and resume

The `logic_train_policy.py` command saves before closing MIDI ports. Its CLI
supervisor allows ten seconds for cleanup, then stops a stuck worker with exit
code 124 and a warning. This bounds native CoreMIDI shutdown hangs; it does not
confirm that Logic received note-off messages. If sound remains, stop it in
Logic. Look for `Saved ...` to confirm persistence. Normal cleanup exits normally.
The supervisor is specific to this CLI example; it does not forcibly exit code
using the Gymnasium environment directly.

The pitch-training example saves weights, optimizer state, random-generator
state, and the parsed session YAML in its checkpoint. It also records the
package version, Python version, and operating system. Resume rejects a changed
session configuration before opening MIDI ports. Moving an unchanged YAML file
is fine. Older checkpoints without session metadata require a new training run;
they are not silently migrated. Only load checkpoints you trust.

The default output file is `artifacts/pitch_policy.pt`; `--checkpoint` selects
another file. Checkpoints do **not** save instrument presets or restore Logic state.
Save the Logic project separately alongside the YAML and checkpoint. Session
YAML can contain local port names and paths; review it before sharing weights.

## Validate a saved experiment

Use a saved test project and quiet monitoring levels. Stop other bridge scripts.
Record the exact Logic and macOS versions with the following live results:

- Run live doctor for the mixed example and confirm the synth parameter names.
- Run the mixed example long enough to play the human track; verify synth notes
  and knobs, trombone notes and bend, and no unintended human-track control.
- Test both finite completion and Ctrl-C, checking for stuck notes afterwards.
- Repeat opening, stepping, and closing in one Python process. Automated tests
  cover this lifecycle with a fake adapter, not native MIDI hardware.
- Save and resume the pitch-training policy; confirm training progress is retained.

For initial setup validation, use **one active Mackie controller** with
configured MIDI tracks. Independent multiple-Mackie operation remains
experimental. Cached LCD text is diagnostic only; it is not a confirmed fresh
parameter value and must not be used as a reward measurement. The included
pitch reward does not depend on cached Mackie values.
