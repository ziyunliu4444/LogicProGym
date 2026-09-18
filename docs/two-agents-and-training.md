# Multi-agent: piano, synthesizer, and trombone

Play a piano while two scripted policies control separate instruments. The synth
plays notes and changes Cutoff through Mackie; the trombone plays notes with
MIDI pitch bend. These are two roles in **one Gymnasium action dictionary**, not
independent Gymnasium environments or a multi-agent learning algorithm. Neither
policy learns or adapts to your performance.

Looking for learning instead? See the [pitch-policy walkthrough](walkthrough-policy-training.md).

## Prepare Logic

Use the [standard installation](logic-setup.md#1-install-logicprogym) and run
commands from the source checkout with its virtual environment active. Save
your project and start at low volume.

| Logic track | Instrument | Note source | Parameter control |
| --- | --- | --- | --- |
| 1 | Piano | Physical keyboard only | Human |
| 2 | Alchemy, 8-Bit Memories | First agent IAC bus, channel 1 | Mackie 2, page 1, slot 2: Cutoff |
| 3 | Sampler, Trombones (or another pitch-bend-capable instrument) | Second agent IAC bus, channel 1 | MIDI pitch bend |

Enable two distinct IAC buses in Audio MIDI Setup. Route each bus exclusively
to its intended instrument, and the keyboard only to Track 1. Both agents must
remain audible independently of track selection. No articulation messages are
sent. Set a nonzero pitch-bend range in the trombone instrument; normalized
bend values are not semitone counts.

Pair Mackie Control 2 with Input `LogicProGym Control 2 To Logic` and Output
`LogicProGym Control 2 From Logic`. The configuration creates two numbered
controller pairs, but Mackie 1 is unused. Follow [endpoint setup](renaming.md#mackie-endpoints)
for first-time pairing while the virtual ports are available. Stop other
Mackie programs before running this example, doctor, or a scanner.

## Configure

```bash
logicprogym devices
cp configs/examples/logic_two_agents.yaml configs/my_multi_session.yaml
```

In the [annotated configuration](../configs/examples/logic_two_agents.yaml), replace:

- `YOUR_KEYBOARD_INPUT`: physical keyboard input.
- `YOUR_AGENT_OUTPUT`: first IAC output, routed to Track 2.
- `YOUR_SECOND_AGENT_OUTPUT`: different IAC output, routed to Track 3.

MIDI `channel: 0` means channel 1. Roles `synth` and `trombone` must keep their
names for this script. The synth exposes notes/velocity plus a one-value Mackie
vector; the trombone exposes notes/velocity plus bend. Human observations do
not authorize agent actions on the piano.

```bash
logicprogym preview configs/my_multi_session.yaml
logicprogym doctor configs/my_multi_session.yaml --live
```

Verify `Cutoff` at page 1, slot 2 for this Alchemy preset. To inspect a different
preset, stop other bridge processes and run:

```bash
logicprogym logic scan configs/my_multi_session.yaml --track synth --pages 1 --output configs/my_synth_parameters.yaml
```

Update names and addresses in your configuration if they differ; the catalog
does not update the session automatically.

## Play and inspect

```bash
python examples/logic_multi_agent.py --config configs/my_multi_session.yaml --steps 100
```

You should hear separate repeating note patterns with rests, changing synth
Cutoff, and trombone pitch bends while your piano remains independently playable.
Logs show held notes, velocity, Cutoff requests, bend requests, human events,
and selected Logic parameter readings with validity and age. Raw cached LCD
text is not returned by the configured environment. No policy weights
are saved; the default reward is zero.

The script sleeps 0.25 seconds between steps, plus control/feedback overhead;
100 steps are not an exact-duration performance. To continue until Ctrl-C:

```bash
python examples/logic_multi_agent.py --config configs/my_multi_session.yaml --steps 0
```

## Stop and troubleshoot

The finite run closes at its step limit; Ctrl-C requests cleanup early. Closing
attempts to release agent notes but does not restore Mackie knob positions.
See [shutdown guidance](shutdown.md) if notes remain after forced termination.

If both agents sound on the same track, correct the IAC routing; changing YAML
role names does not isolate Logic inputs. If the trombone does not bend, check
its channel and instrument bend range. If only Cutoff fails, verify Mackie 2,
Instrument mode, and the preset mapping. This example uses only one active
Mackie controller and does not validate independent simultaneous Mackie control.

## Checkpointed training example

The learning example now has its own [complete walkthrough](walkthrough-policy-training.md),
including task/reward, finite training, checkpoint resume, and evaluation.
