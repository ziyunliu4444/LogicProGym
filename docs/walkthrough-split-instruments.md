# Separate instruments: piano with a scripted synth partner

Play a piano on Logic Track 1 while an agent plays Alchemy on Track 2 and moves
its Robotic and Cutoff macros. The agent cycles MIDI notes 48, 52, 55, and 60;
it is scripted, not a learned accompaniment model, and does not adapt its notes
to your playing. Human MIDI is observed and printed.

## Prepare Logic

Follow the [installation guide](logic-setup.md#1-install-logicprogym), activate
your virtual environment, and run commands from the source checkout. Save a
copy of your project and start at low monitoring volume.

1. Put a piano on Track 1, receiving your physical keyboard.
2. Put Alchemy with **8-Bit Memories** on Track 2.
3. Enable an IAC bus in macOS Audio MIDI Setup and route that bus to Track 2
   only, on MIDI channel 1. Route the keyboard to Track 1 only. Simply naming
   an output in YAML does not create these routes inside Logic. If either
   track receives all inputs, isolate the input ports using the routing
   facilities in your Logic version before proceeding. Both instruments must
   remain playable without relying on whichever track is currently selected.
4. Pair Mackie Control 2 with Input `LogicProGym Control 2 To Logic` and Output
   `LogicProGym Control 2 From Logic`. The YAML creates two numbered pairs but
   controls parameters only through controller 2. See [endpoint setup](renaming.md#mackie-endpoints).
   Ports exist only while connected: for first-time pairing, start the example,
   assign the ports, then stop and rerun if initialization timed out. Run only
   one Mackie bridge process at a time.

## Configure

```bash
logicprogym devices
cp configs/examples/logic_split_tracks.yaml configs/my_split_tracks.yaml
```

In your copy, replace `YOUR_KEYBOARD_INPUT` with the physical keyboard input
name and `YOUR_AGENT_OUTPUT` with the exact IAC output name from the listing.
The [complete annotated YAML](../configs/examples/logic_split_tracks.yaml) defines:

- `human`: MIDI observation only; no agent actions on the piano.
- `agent`: note gates, velocity, pitch bend, expression, sustain, and a two-value
  parameter vector on Track 2. MIDI `channel: 0` means wire channel 1.
- Mackie controller 2, page 1: slot 1 `Robotc`, slot 2 `Cutoff`.

The policy holds one note at a time, with velocity 0.6, neutral pitch bend,
expression 0.75, and sustain off. Only the two macro values oscillate; exposing
an action in YAML does not mean the example varies every action.

```bash
logicprogym preview configs/my_split_tracks.yaml
logicprogym doctor configs/my_split_tracks.yaml --live
```

If the macro names differ, scan before running actions:

```bash
logicprogym logic scan configs/my_split_tracks.yaml --track agent --pages 1 --output configs/my_split_parameters.yaml
```

Use that catalog to update names and addresses in your session copy. Other
Alchemy presets may have different macros even at the same page/slot.

## Play together

```bash
python examples/logic_split_tracks.py configs/my_split_tracks.yaml --steps 120
```

You should hear your piano independently of the agent's repeating synth notes
and macro motion. The terminal prints human events, requested agent notes and
parameter vectors, and reward zero. These are requested controls, not measured
knob values. Open Alchemy manually to watch the controls.

The default is two steps per second, about a minute plus communication overhead.
Use `--steps 0` to continue until Ctrl-C. Normal completion and Ctrl-C attempt
to release agent notes; Mackie macro positions are not restored. Forced process
termination cannot guarantee note release; see [shutdown guidance](shutdown.md).

If your keyboard plays the synth, or the agent plays the piano, fix Logic's MIDI
input routing before continuing. If notes work but macros do not, check Mackie
2's paired ports, Instrument mode, Track 2 assignment, and preset mapping.
No third instrument track is required.
