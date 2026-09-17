# LogicProGym

A Gymnasium interface for learning agents that make music alongside humans in
Logic Pro. Configure what each track can observe and control, then use standard
Gymnasium `reset()`, `step()`, action spaces and wrappers.

**1.0.0 · MIT · macOS + Logic Pro**

## What it supports

- MIDI notes, velocity, pitch bend and user-defined MIDI CC controls.
- Plug-in knob control through learned MIDI CC assignments or Mackie V-Pots.
- Human MIDI note and controller observations.
- Raw audio observations from Logic, or a configured audio input device.
- MIDI-only, Mackie-only or combined control for each agent track.
- Examples for multiple tracks, policy training, human feedback and audio input.

Rewards are task-specific: the default environment reward is zero. The examples
demonstrate possible policies and rewards, not a pretrained musical agent.

## Install

From your local checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

One installation includes all feature dependencies, including training. Choose
features in YAML; no feature extras are required. Native audio capture requires
macOS 14.2+, Apple's command-line tools for the initial helper build, and
system-audio recording permission for the application/helper you run.

## Discover your MIDI devices

Connect your keyboard and enable the virtual MIDI buses you want to use in
macOS Audio MIDI Setup, then run:

```bash
logicprogym devices
```

This lists exact input and output names without sending MIDI or changing Logic.
Use an **input** for human observations and an **output** for agent messages.
It does not automatically configure routing inside Logic.

For machine-readable output, use `logicprogym devices --json`.
Audio-device discovery is separate: `python live_tests/logic_audio_test.py --list`.
Native Logic audio capture does not need an audio-device name.

## First connection check: one agent instrument

Copy a template so your own settings stay separate:

```bash
cp configs/examples/logic_midi_only.yaml configs/my_session.yaml
```

Replace `YOUR_AGENT_OUTPUT` in that file with an exact output name from device
discovery. In Logic, route that bus to the intended software-instrument track.
YAML MIDI channel numbers are zero-based: `channel: 0` means MIDI channel 1.

Then preview, check and run:

```bash
logicprogym preview configs/my_session.yaml
logicprogym doctor configs/my_session.yaml
python live_tests/logic_public_api.py configs/my_session.yaml --steps 100
```

The preview opens no ports. Doctor checks configured port names but cannot prove
your routing inside Logic. The connection check sends notes: start with a comfortable
monitoring volume. Ctrl-C requests shutdown and agent-note cleanup.

## Choose an example

See the [musical-agent catalogue](examples/README.md) for runnable policies.
[Setup tools](tools/README.md) and [manual live checks](live_tests/README.md)
are separate; automated regression tests remain in `tests/`.

The walkthroughs provide concrete musical setups and matching configurations.
Files in `configs/examples/` still require your local MIDI device names;
Alchemy macro mappings are specific to the documented preset.
Replace `YOUR_KEYBOARD_INPUT`, `YOUR_AGENT_OUTPUT` and, where used,
`YOUR_SECOND_AGENT_OUTPUT` with your own names before running.

| Use case | Start here |
| --- | --- |
| Frame-wise observation without agent actions | [Frame observation guide](docs/frame-observations.md) |
| Human notes with agent-controlled timbre | [Shared-instrument walkthrough](docs/walkthrough-shared-instrument.md) |
| Human and agent on separate instruments | [Split-instrument walkthrough](docs/walkthrough-split-instruments.md) |
| MIDI routing smoke check | `logic_midi_only.yaml` + `live_tests/logic_public_api.py` |
| Plug-in knobs through Mackie | `logic_mackie_only.yaml` + [setup guide](docs/logic-setup.md) |
| Pitch-imitation training and checkpoint resume | [Training walkthrough](docs/walkthrough-policy-training.md) |
| Synth MIDI/knobs plus a second MIDI instrument | `logic_two_agents.yaml` + [multi-track guide](docs/two-agents-and-training.md) |
| Learning from human MIDI ratings | [Human feedback guide](docs/human-midi-feedback.md) |
| Hearing audio and moving a mapped knob | [Audio example](docs/audio-input.md#example-an-agent-acts-on-raw-audio) |
| Learning and testing a MIDI knob mapping | [MIDI CC guide](docs/control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi) |

Instrument parameter names and page/slot addresses also depend on your preset.
Scan and verify them before using Mackie templates. The [control modes guide](docs/control-modes.md)
explains how to enable only the actions you want.

## Use Gymnasium directly

```python
import gymnasium as gym
import logicprogym  # Registers the LogicProGym environment.

env = gym.make("LogicProGym/Logic-v0", config_path="configs/my_session.yaml")
try:
    observation, info = env.reset()
    # Your policy chooses actions matching env.action_space.
    action = env.action_space.sample()
    observation, reward, terminated, truncated, info = env.step(action)
finally:
    env.close()
```

Sampling actions can produce notes and change controls. Replace sampling with
your own policy and reward when training; use the documented examples for a
bounded interactive run.

## Limitations and release status

For opt-in step timing, observation freshness, and saving experiment metadata,
see [experiment reproducibility](docs/experiment-reproducibility.md).

Mackie knob actions are relative ticks, not absolute parameter assignments.
Displayed values arrive asynchronously; use validity information, not cached LCD
text, as evidence of a current value. Independent simultaneous Mackie controllers
remain experimental. MIDI/audio timing is real-time, not sample-accurate or an
accelerated offline simulation. The environment does not restore your entire
Logic project on reset. Optional [agent-owned MIDI control resets](docs/reset-controls.md)
can initialize selected CC and pitch-bend values at the start of each episode.

See [support scope](docs/release-status.md) and use the
[live setup checklist](docs/logic-1.0-acceptance.md) to validate your instruments
and routing before an experiment.

## Documentation and development

See the [documentation index](docs/README.md) for setup, examples and experiment
design. Generated Mackie ports start with `LogicProGym Control`; they are
application-created endpoints, not keyboard names. If Logic has stale endpoint
state, follow the [reconnection guide](docs/renaming.md).

## Repository layout

| Folder | Purpose |
| --- | --- |
| `src/logicprogym/` | Environment interface, control adapters, observations, and audio capture |
| `configs/examples/` | Public configurations to copy and customize |
| `examples/` | Musical demonstrations and learning examples |
| `tools/` | MIDI assignment utilities and maintainer packaging checks |
| `live_tests/` | Manual checks requiring your Logic setup |
| `tests/` | Device-free automated tests and their fixtures |
| `docs/` | Setup, walkthroughs, reference, and contributor guides |
| `protocol/` | Bridge message specification |

### Contributing

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

Want to contribute? Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the
[architecture guide](docs/architecture.md) for a code map, extension points and
testing expectations. Documentation improvements and offline tests are welcome;
you do not need a live Logic setup for every contribution.

Only developer test tools are an extra; see the
[support scope](docs/release-status.md) before starting a live experiment.
