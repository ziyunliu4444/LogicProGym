# Human feedback: teach an agent which phrases you prefer

This complete example needs a MIDI keyboard and one audible agent instrument.
It learns a preference over four fixed phrases, not how to generate new music.

## Prepare Logic and configure

Follow the [installation guide](logic-setup.md#1-install-logicprogym), activate
your virtual environment, and run commands from the source checkout.
Use Track 1 for your physical keyboard and mute its audible output. Put any
software instrument on Track 2, with an enabled IAC bus routed exclusively to it
on MIDI channel 1. The keyboard must not also play Track 2. No Mackie setup,
Alchemy preset, audio capture, or third track is required. Start at low volume.

```bash
logicprogym devices
cp configs/examples/logic_human_feedback.yaml configs/my_human_feedback.yaml
```

The [complete annotated YAML](../configs/examples/logic_human_feedback.yaml)
separates agent note output from direct keyboard ratings. MIDI route `channel: 0`
means channel 1; `feedback.channel: 1` uses human-facing numbering. The agent
exposes only note gates and velocity. Four phrases, playback timing, rating
notes, and reward values are all editable in the configuration.

Replace `YOUR_KEYBOARD_INPUT` and `YOUR_AGENT_OUTPUT` in your copy with exact
names from the device listing. The commands below use that configured copy.

This example plays one of four short phrases on the agent instrument through its configured output bus,
then waits five seconds for a rating. A categorical policy learns which
phrases you prefer. Each Gymnasium step includes playback and its response
window; the returned reward is your rating. No Mackie control is involved.

```bash
logicprogym preview configs/my_human_feedback.yaml
logicprogym doctor configs/my_human_feedback.yaml
python examples/logic_human_feedback.py configs/my_human_feedback.yaml --episodes 20 --debug-midi
```

## Listen and rate

Expect `PLAY phrase=... notes=...`, then `RATE now`, then
`RATING ACCEPTED: +1.0` or `-1.0` when a valid rating arrives. Each trial prints
`FEEDBACK`, the update count, and phrase probabilities. With consistent ratings,
preferred phrases should become more likely; twenty trials do not guarantee
convergence. Octave labels vary between keyboards and DAWs: use numeric MIDI
notes, and inspect `--debug-midi` output if unsure.

Use your keyboard or pads on **MIDI channel 1**:

- MIDI note **60**: +1, positive feedback.
- MIDI note **62**: -1, negative feedback.

Only press after `RATE now` appears. The first matching positive-velocity
note-on wins. Release before the next rating. Note-offs, other channels,
unknown notes, and ratings received during playback are ignored. No rating
means **unrated**, no policy update; Gymnasium returns zero as a placeholder
with `info['rated'] = False`. Zero does not mean disapproval.

Edit the YAML's `feedback` section to change the input port, channel (1..16),
rating notes, reward values, phrases and timing. The window is wall-clock
time after playback, not Logic's audio sample clock. Only note/button ratings
are supported in this example; it does not listen for CC ratings.

The program never forwards feedback notes, but Logic may independently receive
the same keyboard. Keep the human Track 1 muted during this rating-only test;
keep the agent instrument unmuted and route only its configured output bus to it.
The template uses channel 1. Stop other test agents first.

## Stop, save, and resume

`--episodes 20` means twenty phrases, including unrated phrases. Ctrl-C releases
notes and saves. Weights, optimizer state, settings, update count and Torch RNG
are saved to `artifacts/human_feedback.pt` (override with `--checkpoint`).

```bash
python examples/logic_human_feedback.py configs/my_human_feedback.yaml --resume
```

Resume rejects changed feedback settings or phrase choices to avoid silently
reinterpreting trained weights. Use a different checkpoint for a new task.
This demonstration is a preference-learning bandit, not a generative musical
model. Live MIDI rating and audio routing still require local verification.

## Feedback troubleshooting

Run with `--debug-midi` to see the received channel and numeric note for each
key press, plus rejection reasons. Debug events are printed during the rating
window; a matching key pressed during playback still does not count.
Logic's selected track or track channel does not change the channel emitted
by the physical keyboard into this direct input.

Channel 1 is the default; use `--feedback-channel N` to match a different
keyboard channel. Keep its audible Logic track muted for this rating-only test. Use
`--checkpoint artifacts/human_feedback_channel1.pt` for a separate run, since
resume requires the same feedback settings. If no MIDI RECEIVED lines appear,
check the configured physical input port. If the channel matches but the note
doesn't, edit positive_note/negative_note to the numeric notes you intend.
