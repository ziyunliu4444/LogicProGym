# Timing, freshness, and reproducible experiments

## Timing diagnostics

Enable in your session YAML:

```yaml
environment:
  timing: true
```

Each step adds `info["timing"]`:
- `step_duration_seconds`: time inside the timing wrapper, including inner
  adapter/audio work, not caller sleep or training between steps.
- `start_interval_seconds`: actual interval between step starts, including
  caller delays; null on the first step after reset.
- `started_monotonic_seconds` and `finished_monotonic_seconds`: process-local
  clock readings, not Logic transport time or UTC.

This measures timing; it does not schedule actions, guarantee a fixed rate,
or detect deadlines without a task-specific target. Instrumentation is opt-in
because wall-clock fields are inherently nondeterministic even with a seed.
You can also use `logicprogym.timing.StepTiming(env)` directly.

## Existing observation freshness

- `audio_valid` marks usable audio samples. `info["audio"]` exposes
  `age_seconds`, `sequence`, sample rate and callback status count.
  Unchanged sequence numbers mean no newly captured block.
- `parameter_valid` distinguishes measured parameter values from unavailable
  entries. Parameter diagnostics in `info["snapshot"].diagnostics` (under
  `mackie` for hybrid sessions) include `parameter_readings`, age and validity.
- MIDI events carry source and sample timestamps; these are not necessarily
  synchronized to the audio callback or Logic transport. Held-note state may
  persist legitimately when no new events arrive.

**Recent does not mean caused by the latest action.** Audio is a rolling window;
Mackie feedback is asynchronous. Neither a cached LCD nor a recent waveform
proves the action has taken effect. There is no general action-acknowledgement
barrier in 1.0. Rewards must respect validity and their task's timing assumptions.

## Save a run manifest

```bash
python live_tests/logic_public_api.py configs/my_session.yaml --steps 100 --seed 42 --manifest artifacts/run-001.json
```

This saves metadata before opening MIDI, even if the subsequent run fails.
The example is a bounded random policy, not a checkpoint evaluator. Its manifest
records the parsed configuration, seed, dependency versions, OS/Python and policy
description. It does not overwrite files. Use a new filename for each run.

For a custom training script:

```python
from logicprogym.experiments import write_manifest

write_manifest(
    "artifacts/training-001.json",
    "configs/my_session.yaml",
    seed=42,
    checkpoint="artifacts/policy.pt",
    labels={"logic_project": "My project", "preset": "My saved preset"},
)
```

An optional existing checkpoint is recorded with SHA-256, not copied or loaded.
Seed your policy and action space too; an environment seed cannot seed Logic
or reproduce a human performance. Review manifests before sharing: YAML may
contain device names and private paths. No audio is recorded by this feature.

## Release acceptance

Automated checks do not establish live hardware correctness. From the clean
repository, repeat the checklist in [live acceptance](logic-1.0-acceptance.md).
Passing on one setup does not certify other instruments or routes. Full Logic project
restoration and deterministic playback remain out of scope.
