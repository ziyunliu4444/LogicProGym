"""Validate audio windows and Gym integration without audio hardware."""

import gymnasium as gym
import numpy as np
import pytest
from logicprogym.audio import AudioInput, AudioObservation


def test_window_mask_rollover_and_reset():
    audio = AudioInput('fake', channels=1, window_frames=4)
    assert not audio.read()[1].any()
    audio._capture(np.array([[.1], [.2]], dtype=np.float32), 2, None, False)
    np.testing.assert_array_equal(audio.read()[1], [0, 0, 1, 1])
    audio._capture(np.array([[.3], [.4], [.5]], dtype=np.float32), 3, None, False)
    np.testing.assert_allclose(audio.read()[0][:, 0], [.2, .3, .4, .5])
    audio._capture(np.array([[.6]], dtype=np.float32), 1, None, True)
    assert audio.read()[1].sum() == 1
    assert audio.read()[2]['callback_status_count'] == 1
    audio.clear()
    assert not audio.read()[1].any()


def test_wrapper_lifecycle_and_spaces():
    class Stream:
        closed = False
        def __init__(self, **kwargs): pass
        def start(self): pass
        def abort(self): pass
        def close(self): self.closed = True

    class Env(gym.Env):
        observation_space = gym.spaces.Dict({'value': gym.spaces.Discrete(1)})
        action_space = gym.spaces.Discrete(1)
        def reset(self, **kwargs):
            super().reset(seed=kwargs.get('seed'))
            return {'value': 0}, {}
        def step(self, action): return {'value': 0}, 2., False, False, {}

    audio = AudioInput('fake', channels=1, window_frames=4, stream_factory=Stream)
    env = AudioObservation(Env(), audio)
    for _ in range(2):
        obs, info = env.reset(seed=1)
        assert env.observation_space.contains(obs)
        audio._capture(np.ones((4, 1), dtype=np.float32), 4, None, False)
        obs, reward, _, _, info = env.step(0)
        assert reward == 2 and obs['audio_valid'].all()
        assert env.observation_space.contains(obs)
        stream = audio.stream
        env.close()
        assert stream.closed


def test_failed_start_closes_stream():
    class Stream:
        closed = False
        def __init__(self, **kwargs): pass
        def start(self): raise RuntimeError('unavailable')
        def abort(self): pass
        def close(self): self.closed = True
    stream = Stream()
    audio = AudioInput('fake', stream_factory=lambda **kwargs: stream)
    with pytest.raises(RuntimeError, match='unavailable'):
        audio.start()
    assert stream.closed and audio.stream is None
