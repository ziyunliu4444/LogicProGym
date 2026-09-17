# Architecture and code map

LogicProGym translates between Gymnasium policy actions and a running music
backend. Logic keeps running between calls: a Python step is not a paused DAW
simulation, and a successful send is not acknowledgment from the instrument.

## Follow one action through the code

```text
Session YAML → config.py → ActionSpec + routing
                            ↓
                 factory.py / gym.make
                            ↓
policy action → env.step → ActionProcessor → backend.apply → Logic
                            ↑                              ↓
policy observation ← ObservationBuilder ← backend.observe
```

Read these files in this order:

| Area | Starting files | Responsibility |
| --- | --- | --- |
| Construction | `src/logicprogym/__init__.py`, `factory.py`, `config.py` | Registration, YAML parsing, validation and optional wrappers |
| Gym lifecycle | `src/logicprogym/env.py` | Connect/reset, apply actions, observe, reward and cleanup |
| Actions | `src/logicprogym/actions/specs.py`, `compiler.py`, `processor.py` | Action definitions, conversions and held-note edge tracking |
| Spaces/state | `src/logicprogym/spaces.py`, `registry.py`, `observations.py` | Fixed shapes, stable slots, state and validity masks |
| Backend contract | `src/logicprogym/backends/base.py`, `adapters/base.py` | Backend-neutral operations and compatibility with adapters |
| Logic I/O | `src/logicprogym/adapters/logic.py`, `logic_hybrid.py`, `logic_mackie.py` | MIDI routes and Mackie control |
| Mackie feedback | `src/logicprogym/adapters/mackie_feedback.py` | Validate asynchronous feedback before exposing values |
| Audio/timing | `src/logicprogym/audio.py`, `native_audio.py`, `frames.py`, `timing.py` | Capture, frame assembly and timing diagnostics |
| Reset policy | `src/logicprogym/reset_controls.py` | Validate explicitly agent-owned absolute baseline commands |
| Research tasks | `src/logicprogym/tasks/`, `wrappers.py`, `examples/` | Task-specific rewards and policies, separate from transport |

Paths in a row share the listed directory unless another directory is specified.
Other backend and recording modules are extension infrastructure, not evidence
that another DAW has been live-validated. See the release's support scope.

## Lifecycle and responsibilities

Construction parses configuration, creates spaces and selects the backend.
Optional audio observation and step timing wrappers are composed in `factory.py`.
Gymnasium may add its own wrappers; for example, `max_episode_steps` adds a time
limit. The base live environment does not choose an episode length.

On first `reset()`, the environment connects and binds discovered tracks and
parameters to slots. On subsequent resets, it releases its tracked agent notes.
It then resets the backend, sends configured baseline commands and resets
observation history. It does not reload a Logic project or automatically capture
knob positions. Frame/audio history has its own reset handling.

`step()` interprets an action, applies commands once, optionally waits for a frame
boundary, then builds an observation from the available snapshot. A held note
gate is state: the processor sends note-on/off at edges rather than retriggering
every step. The backend may report asynchronous or incomplete state.

The factory's reward callback receives `(snapshot, action)`. `FunctionReward`
is a wrapper for `(observation, action, info)` callbacks. They are distinct
interfaces; keep task-specific reward logic out of MIDI and audio transport.
The default reward is zero.

`close()` attempts agent note cleanup and backend closure. Native calls can
stall. The training and reset CLI supervisor bounds worker shutdown separately;
it is not part of the environment API and does not guarantee hardware note release.

## Units and validity that contributors must preserve

- YAML MIDI channels are 0–15; Logic displays channels 1–16. Legacy CLI channel
  flags are 1–16. Convert at boundaries, not repeatedly inside the pipeline.
- Continuous MIDI velocity and CC values are normalized to 0–1; pitch bend uses
  −1–1. MIDI encoding quantizes them. Knob mappings remain the user's responsibility.
- Mackie relative actions request ticks, not absolute knob values. Parameter
  display text, normalized actions and confirmed observations are not interchangeable.
- MIDI frame membership uses local receipt time. Audio uses sample counts anchored
  to an initial receipt, not Logic's transport clock. Missing audio stays invalid.
- Keep observation masks, ages and diagnostic counts intact. Do not replace
  unavailable feedback with an apparently valid zero.

See [frames](frame-observations.md), [parameter observations](parameter-observations.md)
and [reset semantics](reset-controls.md) for details.

## Where to extend the project

Public musical demonstrations live in `examples/`, setup helpers in `tools/`,
and manual hardware checks in `live_tests/`. Automated tests remain in `tests/`.
`src/logicprogym/example_support.py` contains shared demonstration action and
CLI-lifecycle helpers; it does not change the reusable environment's behavior.

- **Existing MIDI control:** start with YAML. A new mapping often needs no Python.
- **New action encoding:** update the action specification/compiler, stateful
  processor if needed, route validation and the relevant backend. Test both
  action-space validation and emitted commands.
- **New observation:** update the builder and declared spaces together. Test
  shape, dtype, masking, reset behavior and capacity limits.
- **New reward/policy:** start in an example or task module, using public wrappers.
- **New backend:** implement the backend contract and capabilities with offline
  tests first. Do not claim live support from a fake backend alone.
- **New CLI example:** keep hardware settings in YAML, retain `try/finally`
  cleanup, document prerequisites and update packaging lists.

Tests such as `test_action_processor.py`, `test_frames.py`, `test_reset_controls.py`
and `test_training_example.py` illustrate injectable backends, fake clocks and
checkpoint testing without Logic. Small tests of contracts are preferable to
tests that merely reproduce the implementation's internal steps.
