"""Offline contracts for ported musical examples; never open live ports."""
import gymnasium as gym
import pytest
from types import SimpleNamespace
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


def test_shared_feedback_prints_reported_percentage_without_midi_or_steps(capsys):
    calls = []
    snapshot = DawSnapshot(diagnostics={'parameter_readings': {'cutoff': {
        'name': 'Cutoff', 'raw': '41.34 %', 'value': .4134,
        'valid': True, 'age_seconds': .1}}})
    def receive():
        calls.append('cache_read')
        return snapshot
    base = SimpleNamespace(adapter=SimpleNamespace(mackie=SimpleNamespace(receive=receive)),
                           _select_snapshot=lambda s: s)
    logic_shared_track.print_after_feedback({'snapshot': DawSnapshot()},
        SimpleNamespace(unwrapped=base), feedback_seconds=0)
    assert calls == ['cache_read']
    output = capsys.readouterr().out
    assert "reported='41.34 %'" in output
    assert '0.4134' not in output


def test_shared_feedback_does_not_print_unselected_readings(capsys):
    base = SimpleNamespace(adapter=SimpleNamespace(mackie=SimpleNamespace(
        receive=lambda: DawSnapshot(diagnostics={'parameter_readings': {'secret': {'raw': '90%'}}}))),
        _select_snapshot=lambda s: DawSnapshot())
    logic_shared_track.print_after_feedback({'snapshot': DawSnapshot()},
        SimpleNamespace(unwrapped=base), feedback_seconds=0)
    assert 'secret' not in capsys.readouterr().out


def test_display_fallback_is_not_confirmed_and_respects_selection(capsys):
    bindings = [dict(id='cutoff', name='Cutoff', controller=1, slot=2),
                dict(id='hidden', name='Secret', controller=1, slot=3)]
    controller = SimpleNamespace(lcd=SimpleNamespace(
        strips=(('', ''), ('Cutoff', '41.34 %'), ('Secret', '90%'))))
    mackie = SimpleNamespace(feedback_bindings=bindings, service=SimpleNamespace(
        bridge=SimpleNamespace(pool=SimpleNamespace(controllers=[controller]))))
    reports = {'cutoff': dict(name='Cutoff', valid=False)}
    logic_shared_track.collect_display_text(mackie, reports)
    assert reports['cutoff']['display_raw'] == '41.34 %'
    assert not reports['cutoff']['valid']
    assert 'raw' not in reports['cutoff'] and 'value' not in reports['cutoff']
    assert 'hidden' not in reports
    logic_shared_track.print_parameter_readings({'snapshot': DawSnapshot(
        diagnostics={'parameter_readings': reports})})
    output = capsys.readouterr().out
    assert "displayed='41.34 %'" in output
    assert 'unverified track/page' in output
    controller.lcd.strips = (('', ''), ('Robotc', '12.00%'))
    reports = {'cutoff': dict(name='Cutoff', valid=False)}
    logic_shared_track.collect_display_text(mackie, reports)
    assert 'display_raw' not in reports['cutoff']


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
    monkeypatch.setattr(logic_shared_track, 'print_after_feedback', lambda *a: None)
    argv = ['demo', 'unused.yaml', '--steps', '3'] + (['--read-only'] if read_only else [])
    monkeypatch.setattr('sys.argv', argv)
    logic_shared_track.main()
    assert lifecycle == ['reset', 'close']
    assert len(actions) == 3
    assert all(np.count_nonzero(a['shared/parameter_vector']) == 0 for a in actions) == read_only
    schema.close()
