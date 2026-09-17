"""Exercise training, persistence, and resume without a live MIDI session."""

import gymnasium as gym
import numpy as np
import torch
import time

from examples import logic_train_policy as example


def _stalled_cleanup(connection):
    connection.send('cleanup')
    time.sleep(60)


def _normal_cleanup(connection):
    connection.send('cleanup')
    connection.close()


def test_supervisor_stops_stalled_cleanup(capsys):
    assert example.supervise(_stalled_cleanup, cleanup_timeout=.2) == 124
    assert 'Note release is not confirmed' in capsys.readouterr().out


def test_supervisor_allows_normal_exit():
    assert example.supervise(_normal_cleanup) == 0


def test_training_checkpoint_resume_and_evaluation(tmp_path, monkeypatch):
    class FakeEnv(gym.Env):
        action_space = gym.spaces.Dict({
            'agent/note_gate': gym.spaces.MultiBinary(128),
            'agent/velocity': gym.spaces.Box(0, 1, (128,), dtype=np.float32),
        })
        observation_space = gym.spaces.Discrete(1)

        def reset(self, **kwargs):
            super().reset(seed=kwargs.get('seed'))
            return 0, {}

        def step(self, action):
            assert self.action_space.contains(action)
            return 0, 0.0, False, True, {}

        def close(self):
            # Persistence must precede cleanup, even when native close stalls.
            assert path.exists()
            assert torch.load(path, weights_only=True)['steps'] >= 1

    monkeypatch.setattr(example.gym, 'make', lambda *a, **k: FakeEnv())
    monkeypatch.setattr(example.PitchCutoffTask, 'human_note', lambda self, obs: 72)
    path = tmp_path / 'policy.pt'
    config = tmp_path / 'session.yaml'
    config.write_text('tracks: []\n')
    argv = ['train', str(config), '--steps', '1', '--checkpoint', str(path)]
    monkeypatch.setattr('sys.argv', argv)
    phases = []
    def on_cleanup():
        assert torch.load(path, weights_only=True)['steps'] == 1
        phases.append('cleanup')
    example.main(on_cleanup=on_cleanup)
    assert phases == ['cleanup']
    assert torch.load(path, weights_only=True)['steps'] == 1
    monkeypatch.setattr('sys.argv', argv + ['--resume'])
    example.main()
    assert torch.load(path, weights_only=True)['steps'] == 2
    before = path.read_bytes()
    monkeypatch.setattr('sys.argv', argv + ['--resume', '--evaluate'])
    example.main()
    assert path.read_bytes() == before
