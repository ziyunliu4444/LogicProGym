# Validate your live setup

See [support scope](release-status.md) for requirements and limitations. Record
the date, Logic/macOS versions, instrument/preset, configuration and result for
each applicable check. A checklist entry is not a claim that it has passed.

Run the applicable checks in a dedicated Logic test project at comfortable
monitoring levels. Keep a backup and repeat relevant checks after changing
instruments, presets, routing, or software versions. Skip features you do not use.

## Installation and setup

- Install with `python -m pip install -e .` from the source checkout.
- Choose a configuration from the [example catalogue](../examples/README.md),
  copy it to a personal session file, and replace its device placeholders.
- `logicprogym doctor SESSION.yaml` identifies missing keyboard or IAC ports.
- `logicprogym doctor SESSION.yaml --live` receives feedback from every configured
  Mackie controller and validates configured parameter names.
- `logicprogym logic scan SESSION.yaml --track agent --pages 2 --output CATALOG.yaml`
  records the visible page/slot/name mapping.

## Live behavior

- Human note-on, note-off, velocity, pitch bend, sustain, and CC input appear
  in observations with human provenance.
- Agent notes, velocity, pitch bend, sustain, CC, and Mackie parameter actions
  reach only their configured tracks.
- Two agent tracks can act in one Gymnasium step without changing the human
  performance track.
- Mackie feedback reports the actual displayed parameter name and value.
- Changed names at configured page/slot addresses fail live validation;
  presets with identical names are not distinguishable by this check.

## Gymnasium behavior

- `logicprogym.make(...)` and `gym.make('LogicProGym/Logic-v0', ...)` construct the same
  environment lazily.
- `reset(seed=...)`, `step`, action/observation spaces, termination, truncation,
  and standard wrappers behave according to Gymnasium's API.
- Task rewards can be added with `logicprogym.FunctionReward` without editing a
  Logic adapter.

## Frame observation

- Follow [frame setup](frame-observations.md) with a configured observation-only
  session. Confirm MIDI events appear in the expected intervals without repeating
  in later frames, while held-note state persists.
- Enable audio at its actual sample rate. Confirm fixed output shape and inspect
  missing-sample masks; do not interpret zero-filled gaps as measured silence.
- Introduce a caller delay and check skipped-frame diagnostics. No action should
  be replayed in a burst to catch up. Check finite completion and Ctrl-C.

## Safety and lifecycle

- With resets disabled, verify existing control positions are preserved.
- Enable only agent-owned MIDI resets as described in `reset-controls.md`.
  Play an agent note with sustain on, then reset: its note must release and
  the configured CC/bend positions must return to their requested values.
- Repeat reset twice in the same process; both must finish, with no hanging
  notes. Play a held note/pedal on the separately routed human track during
  this check and confirm it is unaffected. Do not test on a shared MIDI route.
- Confirm reset info says `sent`, not confirmed; inspect actual values in Logic.
- With `environment.timing: true`, verify positive step duration and realistic
  intervals. Compare audio/Mackie validity and age with changes in Logic.
- Run `python live_tests/logic_public_api.py YOUR_SESSION.yaml --steps 20
  --manifest artifacts/run-001.json`; inspect its seed, parsed
  configuration and versions. Custom training scripts should record their
  checkpoint reference through `write_manifest`.
- Normal completion and one Ctrl-C release active notes, sustain, and sound.
- A finite episode exits at its requested limit.
- `env.close()` returns promptly in a Python process and notebook.
- Reopening an environment does not leave duplicate virtual MIDI endpoints.

The live items must be checked on real hardware; the Python suite covers the
offline protocol, configuration, routing, action, observation, and wrapper
behavior.
