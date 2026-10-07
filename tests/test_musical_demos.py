"""Offline contracts for ported musical examples; never open live ports."""
import gymnasium as gym
import pytest
from logicprogym.models import DawSnapshot
import logicprogym
from examples import logic_shared_track, logic_split_tracks


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
    monkeypatch.setattr(logic_split_tracks.time, 'sleep', lambda _: None)
    monkeypatch.setattr('sys.argv', ['demo', 'unused.yaml', '--steps', '3'])
    logic_split_tracks.main(on_cleanup=lambda: calls.append('cleanup'))
    assert calls == ['reset', 'step', 'step', 'step', 'cleanup', 'close']
    schema.close()


def test_shared_feedback_displays_only_returned_reports(capsys):
    readings = {
        'cutoff': {'name': 'Cutoff', 'raw': '41.34 %', 'value': .4134,
                   'valid': True, 'age_seconds': .1},
        'res': {'name': 'Res', 'raw': '18 %', 'valid': False},
        'thin': {'name': 'Thin', 'valid': False},
        'arp': {'name': 'Arp Md', 'display_raw': 'Off', 'display_age_seconds': 1.2,
                'valid': False},
    }
    snapshot = DawSnapshot(diagnostics={'mackie': {'parameter_readings': readings}})
    logic_shared_track.print_parameter_readings({'snapshot': snapshot})
    output = capsys.readouterr().out
    assert "raw='41.34 %' age=0.1 value=0.4134 valid=True" in output
    assert "raw='18 %' age=None value=None valid=False" in output
    assert "raw=None age=None value=None valid=False" in output
    assert "raw='Off' age=1.2 value=None valid=False" in output


def test_shared_feedback_handles_no_observed_parameters(capsys):
    logic_shared_track.print_parameter_readings({'snapshot': DawSnapshot()})
    assert 'no selected readings' in capsys.readouterr().out


@pytest.mark.parametrize('read_only', [False, True])
def test_shared_demo_calls_environment_and_preserves_read_only(monkeypatch, read_only):
    import numpy as np
    schema = gym.make(logicprogym.ENV_ID,
                      config_path='configs/examples/logic_shared_track.yaml')
    actions, lifecycle = [], []
    class Fake:
        action_space = schema.action_space
        def reset(self):
            lifecycle.append('reset')
            return {}, {}
        def step(self, action):
            assert self.action_space.contains(action)
            actions.append(action)
            return {}, 0., False, False, {}
        def close(self):
            lifecycle.append('close')
    monkeypatch.setattr(gym, 'make', lambda *a, **k: Fake())
    monkeypatch.setattr(logic_shared_track.time, 'sleep', lambda _: None)
    argv = ['demo', 'unused.yaml', '--steps', '3'] + (['--read-only'] if read_only else [])
    monkeypatch.setattr('sys.argv', argv)
    logic_shared_track.main()
    assert lifecycle == ['reset', 'close']
    assert len(actions) == 3
    assert all(np.count_nonzero(a['shared/parameter_vector']) == 0 for a in actions) == read_only
    schema.close()
