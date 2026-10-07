# Checkpoints and resume

The `logic_train_policy.py` command saves before calling the environment’s
`close()`. LogicProGym handles note release and port cleanup, including Ctrl-C
inside environment operations. Examples use `finally` for interrupts between
operations. Look for `Saved ...` to confirm persistence and `Environment closed.`
to confirm that cleanup returned successfully. A native MIDI timeout is a
failure, not confirmed hardware note release; see [shutdown](shutdown.md).

The training examples save weights, optimizer state, random-generator
state, and the parsed session YAML in their checkpoints. They also record the
package version, Python version, and operating system. Resume rejects a changed
session configuration before opening MIDI ports. Moving an unchanged YAML file
is fine. Older checkpoints without session metadata require a new training run;
they are not silently migrated. Only load checkpoints you trust.

The default files are `artifacts/pitch_policy.pt` and `artifacts/human_feedback.pt`;
`--checkpoint` selects another file. Human-feedback checkpoints also validate
the phrase/rating settings, including any feedback-channel override. Checkpoints do **not** save instrument presets or restore Logic state.
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
