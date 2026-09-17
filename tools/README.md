# Setup and maintenance tools

These utilities are not musical-agent policies.

- `logic_midi_learn.py`: sends messages to assist a Logic Learn-mode assignment;
  this is MIDI assignment learning, not RL training.
- `logic_midi_cc_test.py`: verifies an existing mapping. Keep Learn Mode off.
- `release_smoke.py`: maintainer check of installed files, without MIDI I/O;
  included in the source archive.

```bash
python tools/logic_midi_learn.py --port "YOUR_AGENT_OUTPUT" --channel 1 --cc 20
python tools/logic_midi_cc_test.py --port "YOUR_AGENT_OUTPUT" --channel 1 --cc 20
```

These diagnostic helpers retain direct routing flags. Their channels are 1–16;
YAML uses 0–15. Musical examples take routing from YAML. See the [control mapping guide](../docs/control-modes.md)
for assignment settings and troubleshooting. Discover devices with
`logicprogym devices`.
