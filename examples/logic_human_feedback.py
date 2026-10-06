"""Learn phrase preferences from explicit MIDI ratings using Gymnasium.

One LogicProGym environment sends note actions and observes human MIDI.
The training loop plays a phrase, then interprets observed events as a rating. Missing feedback is marked unrated and never trained on.
This is a small preference-learning bandit, not a general music generator.
"""

import argparse
from pathlib import Path
import time

import numpy as np
import torch
import yaml
import logicprogym
from logicprogym.checkpoints import session_metadata, validate_session


def rating(event, settings):
    """Interpret a human note event observed by LogicProGym as a rating."""
    if event.track_id != settings['track'] or event.source != 'human':
        return None
    if event.kind != 'note_on' or event.values.get('velocity', 0) <= 0:
        return None
    if event.values.get('channel') != settings['channel'] - 1:
        return None
    note = event.values.get('note')
    if note == settings['positive_note']:
        return float(settings['positive_reward'])
    if note == settings['negative_note']:
        return float(settings['negative_reward'])
    return None


def validate(settings):
    if not isinstance(settings.get('track'), str) or not settings['track']:
        raise ValueError('feedback.track must name the observed human track')
    if not 1 <= settings['channel'] <= 16:
        raise ValueError('feedback.channel must be 1..16')
    notes = [settings['positive_note'], settings['negative_note']]
    if len(set(notes)) != 2 or any(not 0 <= n <= 127 for n in notes):
        raise ValueError('Feedback notes must be distinct MIDI notes in 0..127')
    for field in ('window_seconds', 'note_seconds', 'gap_seconds'):
        if not np.isfinite(settings[field]) or settings[field] <= 0:
            raise ValueError(f'{field} must be finite and positive')
    if not settings['positive_reward'] > 0 or not settings['negative_reward'] < 0:
        raise ValueError('Ratings must have positive and negative rewards')
    if not all(np.isfinite(settings[k]) for k in ('positive_reward', 'negative_reward')):
        raise ValueError('Rewards must be finite')
    if not settings['phrases'] or any(not p or any(not isinstance(n, int) or not 0 <= n <= 127 for n in p) for p in settings['phrases']):
        raise ValueError('Provide nonempty phrases of MIDI notes in 0..127')


def validate_session_controls(env, config, settings):
    """Check the example's task requirements without changing Gymnasium spaces."""
    if set(env.action_space.spaces) != {'agent/note_gate', 'agent/velocity'}:
        raise ValueError('This example requires an agent track with notes_only actions')
    routes = config['adapter'].get('routes', ())
    if not any(r['track_id'] == settings['track'] and r.get('input_port') and
               r.get('input_source', 'human') == 'human' for r in routes):
        raise ValueError('Configure a human MIDI input route for feedback.track')
    if not any(t['alias'] == settings['track'] and
               {'notes', 'velocity'} <= set(t.get('observe', [])) for t in config['tracks']):
        raise ValueError('Enable notes and velocity observations for feedback.track')


def note_action(note=None):
    """Construct a note action in LogicProGym's existing action space."""
    gates = np.zeros(128, dtype=np.int8)
    if note is not None:
        gates[note] = 1
    return {'agent/note_gate': gates,
            'agent/velocity': np.full(128, 0.60, dtype=np.float32)}


def play_phrase_and_rate(env, settings, phrase_index, *, debug_midi=False):
    """Run one training trial through ordinary LogicProGym steps.

    The score is interpreted by this script, not substituted for env.step's
    reward. None means no rating and therefore no learning update.
    """
    phrase = settings['phrases'][phrase_index]
    print(f'PLAY phrase={phrase_index} notes={phrase}', flush=True)
    for note in phrase:
        observation, _, terminated, truncated, info = env.step(note_action(note))
        if terminated or truncated:
            return None, observation, True, info
        time.sleep(settings['note_seconds'])
        observation, _, terminated, truncated, info = env.step(note_action())
        if terminated or truncated:
            return None, observation, True, info
        time.sleep(settings['gap_seconds'])
    # Drain playback events before opening the rating window.
    observation, _, terminated, truncated, info = env.step(note_action())
    if terminated or truncated:
        return None, observation, True, info
    start = time.monotonic()
    deadline = start + settings['window_seconds']
    print(f"RATE now: channel {settings['channel']}, "
          f"note {settings['positive_note']}=positive / "
          f"{settings['negative_note']}=negative", flush=True)
    score = None
    while True:
        observation, _, terminated, truncated, info = env.step(note_action())
        # Per-step observed events avoid re-rating the numerical event history.
        for event in info['snapshot'].events:
            received = event.values.get('_received_monotonic')
            value = rating(event, settings)
            if debug_midi and event.kind == 'note_on':
                print(f"MIDI OBSERVED track={event.track_id} "
                      f"channel={event.values.get('channel', -1) + 1} "
                      f"note={event.values.get('note')} rating={value}", flush=True)
            if received is not None and start <= received <= deadline and value is not None:
                score = value
                print(f'RATING ACCEPTED: {score:+.1f}', flush=True)
                break
        if score is not None or terminated or truncated or time.monotonic() >= deadline:
            break
        time.sleep(min(.01, max(0, deadline - time.monotonic())))
    return score, observation, terminated or truncated, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config')
    parser.add_argument('--episodes', type=int, default=20, help='Number of phrases including unrated phrases')
    parser.add_argument('--checkpoint', type=Path, default=Path('artifacts/human_feedback.pt'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--feedback-channel', type=int, choices=range(1, 17),
                        help='Override the feedback MIDI channel (1..16)')
    parser.add_argument('--debug-midi', action='store_true',
                        help='Print received note numbers/channels and rejection reasons')
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error('--episodes must be positive')
    torch.manual_seed(args.seed)
    config = yaml.safe_load(Path(args.config).read_text())
    settings = config['feedback']
    if args.feedback_channel is not None:
        settings['channel'] = args.feedback_channel
    validate(settings)
    env = logicprogym.make(args.config)
    validate_session_controls(env, config, settings)
    logits = torch.nn.Parameter(torch.zeros(len(settings['phrases'])))
    optimizer = torch.optim.Adam([logits], lr=0.1)
    updates = 0
    session = session_metadata(args.config)
    if args.resume:
        saved = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
        validate_session(saved, session)
        if saved['settings'] != settings:
            raise ValueError('Checkpoint feedback settings/phrases differ from this configuration')
        with torch.no_grad():
            logits.copy_(saved['logits'])
        optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng'])
        updates = saved['updates']
    try:
        observation, info = env.reset(seed=args.seed)
        for _ in range(args.episodes):
            policy = torch.distributions.Categorical(logits=logits)
            selected = policy.sample()
            reward, observation, finished, info = play_phrase_and_rate(
                env, settings, int(selected), debug_midi=args.debug_midi)
            if reward is not None:
                loss = -policy.log_prob(selected) * reward
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                updates += 1
            print(f"FEEDBACK {'unrated' if reward is None else reward} updates={updates} "
                  f"phrase probabilities={torch.softmax(logits, 0).detach().tolist()}", flush=True)
            if finished:
                break
    except KeyboardInterrupt:
        print('Stopping...', flush=True)
    finally:
        try:
            env.close()
        finally:
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.checkpoint.with_suffix('.tmp')
            torch.save(dict(session=session, settings=settings, logits=logits.detach(), optimizer=optimizer.state_dict(),
                            rng=torch.get_rng_state(), updates=updates), temporary)
            temporary.replace(args.checkpoint)
            print(f'Saved {args.checkpoint}', flush=True)


if __name__ == '__main__':
    main()
