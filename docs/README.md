# Documentation

Start with installation, choose a musical example, then consult the reference
guides as needed. Commands assume a source checkout with the virtual environment
active. Copy public configurations to `configs/my_*.yaml` and set your device
names; personal configurations are not bundled.

## Getting started

- [Install and configure Logic](logic-setup.md)
- [Choose MIDI, Mackie, or combined controls](control-modes.md)
- [Support scope and limitations](release-status.md)
- [Reconnect virtual control surfaces](renaming.md)

## Musical walkthroughs

- [Choose an example](../examples/README.md)
- [Shared instrument: human notes and agent sound shaping](walkthrough-shared-instrument.md)
- [Separate human and agent instruments](walkthrough-split-instruments.md)
- [Two scripted agents alongside a human](two-agents-and-training.md)
- [Pitch-policy training and resume](walkthrough-policy-training.md)
- [Learning from human MIDI ratings](human-midi-feedback.md)
- [Audio-conditioned parameter control](audio-input.md#example-an-agent-acts-on-raw-audio)
- [Frame-wise observation without agent actions](frame-observations.md)

## Setup checks and troubleshooting

- [MIDI assignment tools](../tools/README.md)
- [Manual live checks](../live_tests/README.md)
- [Validate your live setup](logic-1.0-acceptance.md)
- [Audio capture and permissions](audio-input.md)
- [Shutdown and cleanup](shutdown.md)

## Experiment reference

- [Mackie parameter validity](parameter-observations.md)
- [Opt-in control resets](reset-controls.md)
- [Timing, freshness, and run manifests](experiment-reproducibility.md)
- [Checkpoints and resume](checkpoints-and-release.md)

## Contributors and maintainers

- [Contribution guide](../CONTRIBUTING.md)
- [Architecture and extension points](architecture.md)
- [Bridge protocol](../protocol/spec-v1.md)
- [Release packaging checks](final-check.md)
