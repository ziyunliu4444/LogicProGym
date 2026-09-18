# Documentation

You do not need to read every guide. Choose the task below; detailed references
are for when you need them. Commands assume an installed source checkout and an
active virtual environment. Personal `configs/my_*.yaml` files are not bundled.

## Start here

| Your task | Entry point |
| --- | --- |
| Install and connect for the first time | [Logic setup](logic-setup.md) |
| Find devices, inspect/scan knobs, or learn MIDI assignments | [Setup tools](../tools/README.md) |
| Run a musical demonstration or learning policy | [Example catalogue and walkthroughs](../examples/README.md) |
| Define your own tracks, actions, and observations | [YAML tutorial and reference](yaml-configuration.md) |
| Verify audio, reset, routing, or shutdown on your machine | [Live checks](../live_tests/README.md) |

## Troubleshooting

- Wrong or missing Mackie display: [discovery troubleshooting](mackie-discovery.md#understand-the-display-and-troubleshoot).
- Stale endpoints or wrong routing: [reconnect control surfaces](renaming.md).
- MIDI-mapped knob does not move: [assignment guide](control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi).
- Missing audio or recording permission: [audio guide](audio-input.md).
- Notes or processes remain after stopping: [shutdown and cleanup](shutdown.md).

## Experiment reference

- [Supported scope and limitations](release-status.md)
- [Choose MIDI, Mackie, or combined controls](control-modes.md)
- [Mackie parameter validity](parameter-observations.md)
- [Frame-wise MIDI and audio](frame-observations.md)
- [Opt-in control resets](reset-controls.md)
- [Timing, freshness, and run manifests](experiment-reproducibility.md)
- [Checkpoints and resume](checkpoints-and-release.md)
- [Full live acceptance checklist](logic-1.0-acceptance.md)

## Contributors and maintainers

- [Contribution guide](../CONTRIBUTING.md)
- [Architecture and extension points](architecture.md)
- [Bridge protocol](../protocol/spec-v1.md)
- [Release packaging checks](final-check.md)
