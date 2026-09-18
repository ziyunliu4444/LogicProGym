# Choose a musical example

Start with the experience you want, then follow its walkthrough. Each guide
covers Logic setup, the public YAML to copy, device names to edit, commands,
expected behavior, stopping, and troubleshooting. No private files are needed.

| Experience | Type | Walkthrough | Script | Configuration in `configs/examples/` |
| --- | --- | --- | --- | --- |
| Play notes while an agent changes your instrument | Scripted | [Shared instrument](../docs/walkthrough-shared-instrument.md) | `logic_shared_track.py` | `logic_shared_track.yaml` |
| Play alongside a synth agent | Scripted | [Separate instruments](../docs/walkthrough-split-instruments.md) | `logic_split_tracks.py` | `logic_split_tracks.yaml` |
| Play alongside two differently controlled instruments | Scripted | [Multi-agent](../docs/two-agents-and-training.md) | `logic_multi_agent.py` | `logic_two_agents.yaml` |
| Train a policy to imitate your pitch | Learning | [Pitch-policy training](../docs/walkthrough-policy-training.md) | `logic_train_policy.py` | `logic_human_agent.yaml` |
| Rate phrases with your keyboard | Learning | [Human feedback](../docs/human-midi-feedback.md) | `logic_human_feedback.py` | `logic_human_feedback.yaml` |
| Let audio energy drive a knob | Scripted, audio-conditioned | [Audio agent](../docs/audio-input.md#example-an-agent-acts-on-raw-audio) | `logic_audio_agent.py` | `logic_audio_agent.yaml` |
| Inspect MIDI/audio in fixed-duration frames | Observation only | [Frame observer](../docs/frame-observations.md#observation-only-example) | `logic_frame_observer.py` | `logic_frames.yaml` |

To customize a session, use the [YAML tutorial and field reference](../docs/yaml-configuration.md).

## Before starting

Follow the [installation guide](../docs/logic-setup.md#1-install-logicprogym).
Commands assume the source checkout and an activated virtual environment.
Run `logicprogym devices` to discover exact MIDI names. Copy a public YAML to
`configs/my_*.yaml`, then replace its `YOUR_...` placeholders. Personal copies
are Git-ignored. MIDI routes in YAML do not configure routing inside Logic.

Start with low monitoring volume and a saved copy of your Logic project.
Run one example at a time. Use the walkthrough's finite run first, then its
documented continuation option; flags differ between scripts. All support
`--help`, and Ctrl-C requests cleanup. Forced termination cannot guarantee
note release. Parameter changes are not automatically restored on exit.

Only the pitch-training and human-feedback examples update learned policies.
Other examples demonstrate control or observation, and zero default rewards
are expected. Requested actions are not proof of measured knob positions.
Instrument mappings are preset-specific and must be verified locally.

## Examples, tools, and checks are different

- `examples/`: musical behaviors and learning/observation workflows above.
- [tools/](../tools/README.md): configure and verify MIDI knob assignments.
- [live_tests/](../live_tests/README.md): manually check routing, audio, reset,
  and cleanup on your Logic setup.
- `tests/`: automated regression tests that do not require Logic or MIDI hardware.
