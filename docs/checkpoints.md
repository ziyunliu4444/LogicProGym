# Training checkpoints: save, resume, and evaluate

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

Follow the [pitch-policy walkthrough](walkthrough-policy-training.md#stop-save-resume-and-evaluate)
for save, resume, and evaluation commands, or the
[human-feedback walkthrough](human-midi-feedback.md) for phrase preferences.
Confirm that resuming retains training progress and that evaluation does not
overwrite the checkpoint. Keep the session configuration unchanged.

For routing, note release, and reopening checks, use the
[live testing checklist](live-testing.md). Checkpoint persistence does not
establish that the instrument received its controls or returned to its saved state.
