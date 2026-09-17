"""Rating channel isolation and unrated transitions without live MIDI."""
import queue
import time

import gymnasium as gym
import mido
import yaml

from examples.logic_human_feedback import rating, validate, HumanFeedbackEnv


def settings():
    with open('configs/examples/logic_human_feedback.yaml') as stream:
        return yaml.safe_load(stream)['feedback']


def test_ratings_reject_other_channels_noteoffs_and_unknown_notes():
    config = settings()
    validate(config)
    channel = config['channel'] - 1
    assert rating(mido.Message('note_on', channel=channel, note=60, velocity=100), config) == 1
    assert rating(mido.Message('note_on', channel=channel, note=62, velocity=100), config) == -1
    for message in [mido.Message('note_on', channel=(channel + 1) % 16, note=60),
                    mido.Message('note_on', channel=channel, note=60, velocity=0),
                    mido.Message('note_off', channel=channel, note=60),
                    mido.Message('note_on', channel=channel, note=65)]:
        assert rating(message, config) is None


def test_old_feedback_is_not_credited_to_next_phrase(monkeypatch):
    env = HumanFeedbackEnv.__new__(HumanFeedbackEnv)
    env.settings = settings()
    env.settings.update(window_seconds=0.01, note_seconds=0.001, gap_seconds=0.001)
    env.port = object()
    env.action_space = gym.spaces.Discrete(4)
    env.messages = queue.Queue()
    env.messages.put((time.monotonic() - 10, 1.0))
    monkeypatch.setattr(env, 'play', lambda note=None: None)
    _, reward, _, _, info = env.step(0)
    assert reward == 0
    assert not info['rated'] and info['human_reward'] is None
