# Release status and support scope

**Version: 1.0.0.** Live behavior depends on your instruments, routing, and
operating system. Use the [live checklist](logic-1.0-acceptance.md) to validate
the features you plan to use; software tests alone do not verify a Logic setup.

## Requirements

- Python 3.10 or later and Gymnasium 1.x; automated development testing uses Python 3.12.
- macOS and Logic Pro for live integration.
- MIDI routes configured in Logic for the selected tracks.
- Native audio capture additionally requires macOS 14.2 or later, Apple command-line
  tools for the helper build, and system-audio recording permission.

One installation includes MIDI, audio and training dependencies. Only test tools
use an extra: `python -m pip install -e '.[test]'`.

## Available interfaces

- Per-track MIDI-only, Mackie-only or combined control.
- Notes, velocity, pitch bend and explicitly mapped MIDI CC actions.
- Human MIDI input observations, Mackie value diagnostics and optional audio.
- Opt-in [control resets](reset-controls.md), [timing and manifests](experiment-reproducibility.md),
  and [frame observations](frame-observations.md).
- Gymnasium construction through `gym.make("LogicProGym/Logic-v0", config_path=...)`.
  Connections open on reset; always close the environment after use.

Task rewards are configurable; the default is zero. Examples demonstrate the
interface and do not guarantee musical quality or learning convergence.
Articulation requires an instrument-specific mapping supplied by the researcher.

## Important limits

- Direct keyboard input does not describe every edit made in Logic or MIDI
  transformations that Logic applies afterward.
- Mackie actions are relative ticks. LCD feedback is asynchronous; use
  [validity and age diagnostics](parameter-observations.md), not cached text,
  when interpreting numeric values.
- Independent simultaneous Mackie controllers are experimental. Prefer one
  active Mackie controller when evaluating a new setup; multiple MIDI tracks
  can still use distinct routes.
- MIDI messages are serialized, not sample-synchronous across tracks.
- Frame audio uses receipt-time estimates, not sample-accurate alignment to
  MIDI or Logic's transport. Frame mode remains opt-in.
- Reset does not reload a Logic project, preset, transport position or checkpoint.
  Optional reset commands are sent without automatic confirmation from Logic.
- Cleanup after a process crash or SIGKILL cannot be guaranteed.
- Native audio captures the selected application's mix, not isolated stems.
  Full Logic transport/state restoration is outside the release scope.

Use the [live checklist](logic-1.0-acceptance.md) to validate your setup.
Maintainers can use the [release checks](final-check.md) to validate packaging.

## Installed files and licensing

A wheel includes templates, guides and examples under
`<virtual-environment>/share/logicprogym/`. Copy a template to a working
directory and edit its device names before use. A source checkout provides the
same files under `configs/examples/`, `docs/` and `examples/`.

The MIT license applies to this repository's code, not Logic Pro, third-party
plug-ins or instrument samples.
