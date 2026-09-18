# Setup tools

Start here to connect devices, inspect an instrument, or prepare its controls.
These are setup utilities, not agent policies. For musical behavior, choose an
[example](../examples/README.md); for audio/reset/cleanup verification, use the
[live checks](../live_tests/README.md).

Commands assume an [installed checkout](../docs/logic-setup.md#1-install-logicprogym)
with its virtual environment active. Replace `SESSION.yaml` with your own file
and `ALIAS` with its configured track alias. Copy and customize a template first;
see the [YAML guide](../docs/yaml-configuration.md).

## Choose a tool

| I want to… | Command | Details |
| --- | --- | --- |
| Find MIDI input/output names | `logicprogym devices` | [First connection](../README.md#discover-your-midi-devices) |
| Preview controls without opening ports | `logicprogym preview SESSION.yaml` | [Control modes](../docs/control-modes.md) |
| Check configuration and MIDI port names | `logicprogym doctor SESSION.yaml` | [Setup checks](../docs/logic-setup.md#4-check-the-configuration) |
| Verify a Mackie mapping in Logic | `logicprogym doctor SESSION.yaml --live` | [Connection troubleshooting](../docs/renaming.md) |
| Browse pages and manually test knobs | `logicprogym logic inspect SESSION.yaml --track ALIAS` | [Inspector commands](../docs/mackie-discovery.md#interactive-inspector) |
| Discover names and page/slot addresses | `logicprogym logic scan SESSION.yaml --track ALIAS --all --output configs/my_instrument.yaml` | [Discovery and catalogs](../docs/mackie-discovery.md) |
| Assign a MIDI CC to a plug-in knob | `python tools/logic_midi_learn.py --port "YOUR_AGENT_OUTPUT" --channel 1 --cc 20` | [Assignment walkthrough](../docs/control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi) |
| Test an existing MIDI assignment | `python tools/logic_midi_cc_test.py --port "YOUR_AGENT_OUTPUT" --channel 1 --cc 20` | [Assignment walkthrough](../docs/control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi) |

The `logicprogym` commands are implemented in the installed package, not as
scripts in this folder. Both kinds of tools are listed here so you do not have
to search the source tree to find them.

## Before connecting

- Stop other Mackie agents, inspectors, and scanners using the same endpoints.
- `inspect` is interactive: wait for `mackie>`, then enter `lcd`, `left`, `right`,
  or `help`. `scan` is not interactive. Start with `--pages 2` instead of `--all`
  for a short scan.
- Inspector `vpot` commands and MIDI assignment utilities change knob positions;
  save your Logic project first. A scan navigates pages but does not turn knobs.
- MIDI assignment “learning” is Logic's mapping process, not RL training.
  Keep Learn Mode **off** when testing an existing assignment.
- These MIDI helper scripts use channels **1–16**; YAML uses **0–15**.
  CC20 is an example, not a universal cutoff mapping.

For a new instrument with no known parameter names, start with
`configs/examples/logic_discovery.yaml` and follow the
[discovery guide](../docs/mackie-discovery.md#start-without-parameter-names).

## Maintainers

`release_smoke.py` checks installed package files without MIDI I/O. It is not a
musical example or a live routing test. See [release packaging checks](../docs/final-check.md)
for the complete procedure.
