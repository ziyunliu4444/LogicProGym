"""Offline contracts for ported musical examples; never open live ports."""
import gymnasium as gym
import pytest
import logicprogym
from examples import logic_shared_track, logic_split_tracks
from logicprogym import example_support


@pytest.mark.parametrize('module,template', [
    (logic_shared_track, 'logic_shared_track.yaml'),
    (logic_split_tracks, 'logic_split_tracks.yaml'),
])
def test_policy_matches_public_template(module, template):
    env = gym.make(logicprogym.ENV_ID, config_path='configs/examples/'+template)
    try:
        for step in range(100):
            assert env.action_space.contains(module.agent_action(step, 2.0))
        if module is logic_shared_track:
            assert list(env.action_space.spaces) == ['shared/parameter_vector']
        else:
            assert module.agent_action(0, 2)['agent/note_gate'][48] == 1
            assert module.agent_action(2, 2)['agent/note_gate'][52] == 1
    finally:
        env.close()


def test_demo_runs_bounded_and_closes(monkeypatch):
    schema = gym.make(logicprogym.ENV_ID,
                      config_path='configs/examples/logic_split_tracks.yaml')
    calls = []
    class Fake:
        action_space = schema.action_space
        def reset(self):
            calls.append('reset')
            return {}, {}
        def step(self, action):
            calls.append('step')
            return {}, 0., False, False, {}
        def close(self):
            calls.append('close')
    monkeypatch.setattr(gym, 'make', lambda *a, **k: Fake())
    monkeypatch.setattr(example_support.time, 'sleep', lambda _: None)
    monkeypatch.setattr('sys.argv', ['demo', 'unused.yaml', '--steps', '3'])
    logic_split_tracks.main(on_cleanup=lambda: calls.append('cleanup'))
    assert calls == ['reset', 'step', 'step', 'step', 'cleanup', 'close']
    schema.close()
