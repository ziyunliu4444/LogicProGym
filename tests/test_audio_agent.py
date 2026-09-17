"""Verify waveform-conditioned actions and a finite public example episode."""

import gymnasium as gym
import numpy as np

from examples import logic_audio_agent as example


def observation(amplitude, valid=True):
    return {'audio': np.full((16, 2), amplitude, dtype=np.float32),
            'audio_valid': np.full(16, valid, dtype=np.int8)}


def test_audio_drives_knob_and_stale_audio_holds():
    policy = example.AudioEnergyPolicy()
    quiet, _ = policy.act(observation(0), {'audio': {'sequence': 1}})
    loud, details = policy.act(observation(.5), {'audio': {'sequence': 2}})
    assert loud[0] > quiet[0] and details['status'] == 'listening'
    repeated, details = policy.act(observation(0), {'audio': {'sequence': 2}})
    np.testing.assert_array_equal(repeated, loud)
    assert details['status'] == 'waiting/holding'
    invalid, _ = policy.act(observation(0, False), {'audio': {'sequence': 3}})
    np.testing.assert_array_equal(invalid, loud)


def test_example_terminates_and_closes(monkeypatch, capsys):
    class FakeEnv(gym.Env):
        observation_space = gym.spaces.Dict({
            'audio': gym.spaces.Box(-1, 1, (16, 2), dtype=np.float32),
            'audio_valid': gym.spaces.MultiBinary(16)})
        action_space = gym.spaces.Dict({'synth/cutoff': gym.spaces.Box(0, 1, (1,), dtype=np.float32)})
        closed = False
        count = 0
        def reset(self, **kwargs): return observation(.1), {'audio': {'sequence': 1}}
        def step(self, action):
            assert self.action_space.contains(action)
            self.count += 1
            return observation(.1), 0., False, False, {'audio': {'sequence': self.count + 1}}
        def close(self): self.closed = True

    base = FakeEnv()
    monkeypatch.setattr(example.gym, 'make', lambda *a, **kw: gym.wrappers.TimeLimit(base, kw['max_episode_steps']))
    monkeypatch.setattr(example.time, 'sleep', lambda _: None)
    monkeypatch.setattr('sys.argv', ['agent', '--steps', '3'])
    example.main()
    assert base.count == 3 and base.closed
    assert 'requested CC20=' in capsys.readouterr().out
