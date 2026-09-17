"""Learn phrase preferences from explicit MIDI ratings using Gymnasium.

Each Gym step plays one selected phrase and collects the first rating during
the response window. Missing feedback is marked unrated and never trained on.
This is a small preference-learning bandit, not a general music generator.
"""

import argparse
from pathlib import Path
import queue
import threading
import time

import gymnasium as gym
import mido
import numpy as np
import torch
import yaml
import logicprogym
from logicprogym.checkpoints import session_metadata, validate_session


def rating(message, settings):
    """Only positive-velocity note-on events on the feedback channel count."""
    if message.type != 'note_on' or message.velocity == 0:
        return None
    if message.channel != settings['channel'] - 1:
        return None
    if message.note == settings['positive_note']:
        return float(settings['positive_reward'])
    if message.note == settings['negative_note']:
        return float(settings['negative_reward'])
    return None


def validate(settings):
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


class HumanFeedbackEnv(gym.Env):
    """One action selects a phrase; one reward is an explicit human rating."""

    def __init__(self, config, *, feedback_channel=None, debug_midi=False):
        self.settings = yaml.safe_load(Path(config).read_text())['feedback']
        if feedback_channel is not None:
            self.settings['channel'] = feedback_channel
        validate(self.settings)
        self.debug_midi = debug_midi
        self.debug_messages = queue.Queue(maxsize=128)
        self.music = logicprogym.make(config)
        expected = {'agent/note_gate', 'agent/velocity'}
        if set(self.music.action_space.spaces) != expected:
            raise ValueError('This example requires an agent track with notes_only actions')
        self.action_space = gym.spaces.Discrete(len(self.settings['phrases']))
        self.observation_space = gym.spaces.Box(0, 1, (1,), dtype=np.float32)
        self.messages = queue.Queue(maxsize=128)
        self.port = None

    def capture(self, message):
        score = rating(message, self.settings)
        if self.debug_midi and message.type == 'note_on' and message.velocity > 0:
            reason = ('wrong channel' if message.channel != self.settings['channel'] - 1
                      else 'wrong note' if score is None else 'matches rating mapping')
            try:
                self.debug_messages.put_nowait(
                    f'MIDI RECEIVED channel={message.channel + 1} note={message.note} '
                    f'velocity={message.velocity}: {reason}'
                )
            except queue.Full:
                pass
        if score is not None:
            try:
                self.messages.put_nowait((time.monotonic(), score))
            except queue.Full:
                pass

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self.port is None:
            self.port = mido.open_input(self.settings['input_port'], callback=self.capture)
        print(f"Feedback input: {self.settings['input_port']!r}, channel={self.settings['channel']}", flush=True)
        self.music.reset(seed=seed)
        return np.zeros(1, dtype=np.float32), {}

    def play(self, note=None):
        gates = np.zeros(128, dtype=np.int8)
        if note is not None:
            gates[note] = 1
        self.music.step({'agent/note_gate': gates,
                         'agent/velocity': np.full(128, 0.60, dtype=np.float32)})

    def step(self, action):
        if not self.action_space.contains(action):
            raise ValueError('Invalid phrase index')
        if self.port is None:
            raise RuntimeError('Call reset before step')
        phrase = self.settings['phrases'][int(action)]
        print(f'PLAY phrase={int(action)} notes={phrase}', flush=True)
        for note in phrase:
            self.play(note)
            time.sleep(self.settings['note_seconds'])
            self.play()
            time.sleep(self.settings['gap_seconds'])
        # Discard ratings made during the phrase or a previous response window.
        start = time.monotonic()
        deadline = start + self.settings['window_seconds']
        print(f"RATE now: channel {self.settings['channel']}, "
              f"note {self.settings['positive_note']}=positive / "
              f"{self.settings['negative_note']}=negative", flush=True)
        score = None
        while time.monotonic() < deadline:
            if getattr(self, 'debug_midi', False):
                while True:
                    try:
                        print(self.debug_messages.get_nowait(), flush=True)
                    except queue.Empty:
                        break
            try:
                timestamp, value = self.messages.get(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if start <= timestamp <= deadline:
                score = value
                print(f'RATING ACCEPTED: {score:+.1f}', flush=True)
                break
            if getattr(self, 'debug_midi', False):
                print('Rating ignored: received outside the current response window', flush=True)
        return np.zeros(1, dtype=np.float32), 0.0 if score is None else score, False, False, {
            'rated': score is not None, 'phrase': int(action), 'human_reward': score,
        }

    def close(self):
        try:
            self.music.close()
        finally:
            if self.port is not None:
                port, self.port = self.port, None
                errors = []
                def close_port():
                    try:
                        port.close()
                    except BaseException as error:
                        errors.append(error)
                worker = threading.Thread(target=close_port, daemon=True)
                worker.start()
                worker.join(3)
                if worker.is_alive():
                    raise TimeoutError('Feedback MIDI input cleanup is still pending')
                if errors:
                    raise RuntimeError('Feedback MIDI input cleanup failed') from errors[0]


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
    base = HumanFeedbackEnv(args.config, feedback_channel=args.feedback_channel, debug_midi=args.debug_midi)
    env = gym.wrappers.RecordEpisodeStatistics(gym.wrappers.TimeLimit(base, max_episode_steps=args.episodes))
    logits = torch.nn.Parameter(torch.zeros(base.action_space.n))
    optimizer = torch.optim.Adam([logits], lr=0.1)
    updates = 0
    session = session_metadata(args.config)
    if args.resume:
        saved = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
        validate_session(saved, session)
        if saved['settings'] != base.settings:
            raise ValueError('Checkpoint feedback settings/phrases differ from this configuration')
        with torch.no_grad():
            logits.copy_(saved['logits'])
        optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng'])
        updates = saved['updates']
    try:
        env.reset(seed=args.seed)
        for _ in range(args.episodes):
            policy = torch.distributions.Categorical(logits=logits)
            selected = policy.sample()
            _, reward, terminated, truncated, info = env.step(int(selected))
            if info['rated']:
                loss = -policy.log_prob(selected) * reward
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                updates += 1
            print(f"FEEDBACK {'unrated' if not info['rated'] else reward} updates={updates} "
                  f"phrase probabilities={torch.softmax(logits, 0).detach().tolist()}", flush=True)
            if terminated or truncated:
                break
    except KeyboardInterrupt:
        print('Stopping...', flush=True)
    finally:
        try:
            env.close()
        finally:
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.checkpoint.with_suffix('.tmp')
            torch.save(dict(session=session, settings=base.settings, logits=logits.detach(), optimizer=optimizer.state_dict(),
                            rng=torch.get_rng_state(), updates=updates), temporary)
            temporary.replace(args.checkpoint)
            print(f'Saved {args.checkpoint}', flush=True)


if __name__ == '__main__':
    main()
