# Shared instrument: you play, the agent shapes the sound

This worked example uses Alchemy's **8-Bit Memories** preset on Logic Track 1.
You supply every note; a scripted policy moves eight instrument macros through
Mackie Control. It does not learn, send notes, or listen to audio.

## Prepare Logic

Install from a source checkout using the [setup guide](logic-setup.md#1-install-logicprogym).
Run all commands below from that checkout with its virtual environment active.
Save a copy of your Logic project and lower monitoring volume before starting.

1. Put Alchemy on software-instrument Track 1 and load **8-Bit Memories**.
   If this preset is unavailable, choose another instrument only after scanning
   and updating its parameter mappings; these addresses are not universal.
2. Select/enable Track 1 for your keyboard and verify that you can play it.
3. Use Mackie Control 1 for this track. In Logic's Control Surfaces Setup, pair
   Input `LogicProGym Control 1 To Logic` with Output
   `LogicProGym Control 1 From Logic`. The configuration creates two numbered
   controller pairs, but this example sends parameter actions only to controller 1.
   See [endpoint setup](renaming.md#mackie-endpoints): virtual ports appear only
   while connected. On first setup, start the example to expose the ports, pair
   them, then stop and rerun if connection initialization timed out. Do not run
   another Mackie agent or scanner at the same time.

## Configure

```bash
logicprogym devices
cp configs/examples/logic_shared_track.yaml configs/my_shared_track.yaml
```

Edit `configs/my_shared_track.yaml`: replace `YOUR_KEYBOARD_INPUT` with the exact
input name listed for your physical keyboard. Leave the quotes around the name.
The [complete annotated configuration](../configs/examples/logic_shared_track.yaml)
contains the following first-page mapping:

| Slot | Display name | Role |
| --- | --- | --- |
| 1 | Robotc | Robotic macro |
| 2 | Cutoff | Cutoff macro |
| 3 | Arp Md | Arpeggiator mode |
| 4 | Thin | Thin macro |
| 5 | Porto | Portamento macro |
| 6 | Res | Resonance macro |
| 7 | ArpRat | Arpeggiator rate |
| 8 | ArpOct | Arpeggiator octave macro |

`track: 1` is the one-based Logic track index; `controller: 1` selects Mackie 1.
The eight-element `parameter_vector` follows this slot order. No MIDI output
route or note action is exposed to the agent. Human MIDI observations come
directly from the configured keyboard input, not from every edit inside Logic.

Verify the configuration and visible parameter mapping:

```bash
logicprogym preview configs/my_shared_track.yaml
logicprogym doctor configs/my_shared_track.yaml --live
```

If the preset layout differs, stop other bridge processes and inspect it with:

```bash
logicprogym logic scan configs/my_shared_track.yaml --track shared --pages 1 --output configs/my_shared_parameters.yaml
```

Update both parameter names and page/slot addresses if necessary. A catalog
does not automatically replace your configuration.

## Play

```bash
python examples/logic_shared_track.py configs/my_shared_track.yaml --steps 120
```

Play and hold notes. You should hear changing timbre while the terminal prints
human MIDI events and requested parameter vectors. Open Alchemy manually if
you want to watch its macros; automatic window opening is not required.
The script requests two steps per second (about a minute for 120 steps, plus
communication overhead). Reward stays zero because this is a scripted example.
Printed actions are requests, not confirmed knob positions.

Use `--steps 0` for an open-ended session, and Ctrl-C to stop. The script also
stops at its step limit. Mackie positions are **not restored** on exit. Restore
your saved preset/project to return to the original sound. Although the agent
sends no notes, changing arpeggiator controls can change note generation inside
the instrument; this is not a guarantee of silence when keys are released.

If no knobs move, check the controller's To/From pairing, Instrument mode,
track index, and preset mapping. A pan or instrument-selection display is not
the expected macro page. Do not delete unrelated controller assignments.
