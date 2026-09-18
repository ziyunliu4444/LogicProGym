# Manual live integration checks

These scripts exercise routing and lifecycle behavior, not learned musical
behavior. Use a backed-up test project at comfortable monitoring levels.

Need to discover devices, inspect Mackie pages, or create a knob assignment first?
Start with [setup tools](../tools/README.md). For musical demonstrations, see
[examples](../examples/README.md).

| Script | Purpose |
| --- | --- |
| `logic_public_api.py` | Bounded random controls, diagnostics and cleanup |
| `logic_audio_test.py` | Source discovery, permissions, audio signal and validity |
| `logic_reset_test.py` | Held-note, sustain and bend reset checks |
| `logic_cutoff_reset_test.py` | Configured CC20 cutoff baseline restoration |

Copy the required configuration first (choose a new filename if it already exists):

```bash
logicprogym devices
cp configs/examples/logic_midi_only.yaml configs/my_session.yaml
cp configs/examples/logic_cutoff_reset.yaml configs/my_cutoff_reset.yaml
```

Replace device placeholders in both copies, route the agent bus to its intended
Logic track, and complete the [CC20 assignment](../docs/control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi)
before running the cutoff check. Then run the checks individually:

```bash
python live_tests/logic_public_api.py configs/my_session.yaml --steps 20
python live_tests/logic_audio_test.py --source native --seconds 30
python live_tests/logic_cutoff_reset_test.py configs/my_cutoff_reset.yaml
```

A printed request does
not confirm that Logic applied it. Inspect the actual instrument, note release
and human-track behavior. See the [live checklist](../docs/logic-1.0-acceptance.md) and
[reset guide](../docs/reset-controls.md). Device-free regression tests remain in `tests/`.
