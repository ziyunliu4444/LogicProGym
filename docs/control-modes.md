# Choose what agents control

For complete configuration syntax, defaults, and custom-action examples, see
the [YAML tutorial and field reference](yaml-configuration.md).

If an existing CC assignment stops responding, verify its input bus, channel,
CC number and target instrument. Prefer a fixed agent channel strip over
Selected Track when the human plays another track. Use Unsigned / Scaled and
a variable 0..127 value. If these match but control still fails, relearn only
that assignment and turn Learn Mode off before testing again. Do not delete
all assignments. YAML specifies messages; it does not create Logic assignments.

Copy a template, edit its routes and actions, then preview before connecting:

| Mode | Template |
| --- | --- |
| MIDI only | `configs/examples/logic_midi_only.yaml` |
| Mackie only | `configs/examples/logic_mackie_only.yaml` |
| Both MIDI and Mackie | `configs/examples/logic_human_agent.yaml` |
| Mixed roles across tracks | `configs/examples/logic_two_agents.yaml` |

```bash
cp configs/examples/logic_midi_only.yaml configs/my_midi_session.yaml
```

Set the copied file’s output port using `logicprogym devices`, then run:

```bash
logicprogym preview configs/my_midi_session.yaml
python live_tests/logic_public_api.py configs/my_midi_session.yaml --steps 100
```

The preview constructs spaces without opening ports. The test samples enabled
actions only. It holds middle C on each note-gate track to limit polyphony;
other enabled controls are random. It is a connection test, not a learner.

Use `logic_hybrid` for a session mixing transports. Each track independently
selects controls under `actions`: MIDI targets require a MIDI output route;
plugin targets require a Mackie assignment. The public constructor rejects
missing output routes before connecting. Merely configuring a transport does
not add actions. Presets are optional: use an action list to specify controls
individually, or a preset plus `add` for convenience. Remove the preset to omit
its controls. Custom IDs such as `bend` are allowed; targets define behavior.

MIDI CC availability does not imply that an instrument responds to that CC.
Mackie page/slot bindings must be verified for the selected instrument.
See [parameter observations](parameter-observations.md) for numeric readings,
validity masks, and human-readable diagnostics.

## Let the agent control a Logic plug-in knob using MIDI

This setup enables an agent to control a plug-in knob by sending MIDI Control
Change (CC) messages through its MIDI output bus. You assign a CC number to a
specific knob once in Logic. Afterward, the agent can change that knob by sending
different values on the same MIDI port, channel and CC number.

For example, assign **CC20 on channel 1 from YOUR_AGENT_OUTPUT** to the synth's
**Cutoff** knob. The agent can then send CC20 values from 0 to 127 to set Cutoff
to different positions. A physical MIDI knob is not required: the learning
script generates the MIDI messages that Logic learns. This mapped knob can be
controlled without sending Mackie V-Pot commands.

In a LogicProGym action configuration, the corresponding transport target is
`midi.cc.20`. The action's track must have a MIDI output route matching the bus
and channel used for the Logic assignment. Changing the CC number in YAML does
not create the assignment in Logic; complete the one-time mapping below first.

This enables control. Reading the resulting plug-in value is a separate
capability; a sent CC value alone does not confirm the knob's actual value.

For an absolute MIDI CC mapping, open
**Logic Pro > Control Surfaces > Controller Assignments > Expert View** and use:

| Setting | Value |
| --- | --- |
| Format | **Unsigned** |
| Mode | **Scaled** |
| Incoming minimum / maximum | **0 / 127** |
| Multiply | **1.00** |

Scaled maps the incoming MIDI range onto the destination parameter's range.
Use it for this absolute knob assignment, rather than Direct or Relative.
The displayed plugin percentage need not equal the CC value divided by 127.
See [Apple's value parameter documentation](https://support.apple.com/guide/logicpro/expert-view-value-parameters-ctls71c308ee/12.3/mac/15.6).

Run these commands from an installed source checkout. Replace
`YOUR_AGENT_OUTPUT` with an exact output name from `logicprogym devices`.
For a new assignment, start:

```bash
python tools/logic_midi_learn.py --port "YOUR_AGENT_OUTPUT" --channel 1 --cc 20
```

Select the destination knob in the instrument window. Choose **Learn Assignment
for Cutoff** (or your intended parameter), and check the destination really is
that parameter. When prompted, press Enter in the script to send a gradual CC
sweep. Turn **Learn Mode off** when the sweep finishes, set the values above,
then use the script's test console. Use an unassigned CC; CC20 is only the
example mapping, not a universal Cutoff controller number.

Check that the input uses the agent's bus, channel 1 and CC20, with a variable
value (`Lo7` in the message pattern), rather than matching only a literal 64.
If the destination says **Open Controller Assignments**, it is the wrong
assignment. Correct only that assignment; do not delete the Mackie assignments
or reset all control surfaces.

To check an existing assignment later, keep **Learn Mode off** and run:

```bash
python tools/logic_midi_cc_test.py --port "YOUR_AGENT_OUTPUT" --channel 1 --cc 20
```

The test sends `32, 64, 96, 64, 64`, two seconds apart, and stops automatically.
The knob should move to repeatable positions; the final repeated 64 should
produce no further movement. Ctrl-C also stops the script. The final setting
remains in Logic. These scripts print sent CC values, not measured plugin
values, and do not automatically operate Logic's Learn Mode.

Verify the assignment still targets the intended instrument after selecting
another track. A mapping that follows the selected track needs adjustment
before use in a multi-track session.
