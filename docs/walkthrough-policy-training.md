# Train a pitch-imitation policy

Play notes on a piano while a small neural policy learns to choose the same MIDI
pitch on a second instrument. This demonstrates Gymnasium learning and checkpoint
resume, not a musically sophisticated accompanist. It uses incoming MIDI, not
audio pitch detection or a Cutoff reward.

## Prepare Logic and configure

Follow the [setup guide](logic-setup.md): Track 1 is your keyboard/piano;
Track 2 is the agent instrument on a separate IAC input. For the supplied hybrid
configuration, use Alchemy's **8-Bit Memories** and Mackie 2 on Track 2, with
`Robotc` and `Cutoff` at page 1, slots 1 and 2. Match the controller's numbered
To/From ports as described in [endpoint setup](renaming.md#mackie-endpoints).
No third track is needed. Save your project and lower monitoring volume.

From an installed source checkout with the virtual environment active:

```bash
logicprogym devices
cp configs/examples/logic_human_agent.yaml configs/my_training_session.yaml
```

Replace the keyboard and agent-output placeholders with the exact port names.
Route the keyboard exclusively to Track 1 and the IAC output exclusively to
Track 2. The [annotated YAML](../configs/examples/logic_human_agent.yaml) exposes
human note observations and agent controls. This policy varies only the agent's
note choice; Mackie parameter actions stay zero. The supplied configuration still
connects to Mackie, so its assignments must be valid even though knobs do not move.
Keep the agent role named `agent`, unless also passing `--track`.

```bash
logicprogym preview configs/my_training_session.yaml
logicprogym doctor configs/my_training_session.yaml --live
```

## Train

```bash
python examples/logic_train_policy.py configs/my_training_session.yaml --steps 100 --checkpoint artifacts/pitch_walkthrough.pt
```

Play and hold one note at a time to make the task clear. The policy chooses among
128 MIDI pitches, so early output may sound unrelated or fall outside a sampled
instrument's audible range. Logs report `step`, `human`, `agent`, and `reward`.
No observed human note produces `human=None agent=None reward=+0.0000`; those
silent polling steps still count toward the limit.

Reward is `-abs(agent_pitch - human_pitch) / 127`: exact pitch matches receive
0, and mismatches receive negative values. The target is the human observation
used to choose the action, not a later keyboard event. Training updates only
when a human target is present. A short run checks integration, not convergence.
Steps include a 0.25-second pause plus communication overhead.

## Stop, save, resume, and evaluate

The run stops after 100 steps; Ctrl-C stops early. Training saves policy weights,
optimizer state, baseline, cumulative step count, and Torch random state before
cleanup. Look for `Saved artifacts/pitch_walkthrough.pt` and shutdown output.
The CLI supervises cleanup; forced termination still cannot confirm MIDI release.

Continue for 100 **additional** steps using the same configuration:

```bash
python examples/logic_train_policy.py configs/my_training_session.yaml --steps 100 --checkpoint artifacts/pitch_walkthrough.pt --resume
```

Evaluate without updating or overwriting that checkpoint:

```bash
python examples/logic_train_policy.py configs/my_training_session.yaml --steps 100 --checkpoint artifacts/pitch_walkthrough.pt --resume --evaluate
```

Evaluation chooses the highest-scoring pitch instead of sampling. Resume checks
configuration compatibility; do not edit the task configuration between these
commands. For a different task, choose a new checkpoint path. A checkpoint does
not restore your Logic project, knob positions, routing, or human performance.
Save the Logic project separately. See [checkpoint details](checkpoints-and-release.md).

## Troubleshoot

- Always `human=None`: check the physical input name and play/hold notes during
  the run. Logic's track selection is not the program's MIDI input selection.
- Agent notes printed but silent: check IAC routing, channel, instrument range,
  and track mute state.
- Mackie setup fails: verify the supplied preset/page/slot mapping using the
  [setup guide](logic-setup.md); do not rename parameters merely to pass a check.
- Reward does not improve: collect more rated-by-pitch interaction and verify
  observations first. This small live example provides no convergence guarantee.
