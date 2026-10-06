"""Human ratings use LogicProGym's real action/observation pipeline, without hardware."""
from pathlib import Path

import mido
import numpy as np
import pytest
import yaml

import logicprogym
from logicprogym.adapters.logic import LogicMidiAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv
from logicprogym.models import DawEvent, EventSource
from examples import logic_human_feedback as example
from tests.test_logic_midi_adapter import FakeMidiBackend


def make_task(monkeypatch, tmp_path, scheduled=()):
    settings = yaml.safe_load(Path('configs/examples/logic_human_feedback.yaml').read_text())
    settings['feedback'].update(note_seconds=.02, gap_seconds=.01, window_seconds=.1)
    path = tmp_path / 'feedback.yaml'
    path.write_text(yaml.safe_dump(settings))
    config = LogicProGymConfig.from_yaml(path)
    backend = FakeMidiBackend()
    adapter = LogicMidiAdapter.from_config(config.adapter, midi_backend=backend)
    music = LogicProEnv.from_config(adapter, config)
    monkeypatch.setattr(logicprogym, 'make', lambda _: music)
    clock = [0.0]
    monkeypatch.setattr('logicprogym.adapters.logic.monotonic', lambda: clock[0])
    monkeypatch.setattr(example.time, 'monotonic', lambda: clock[0])
    pending = list(scheduled)
    def sleep(duration):
        end = clock[0] + duration
        while pending and pending[0][0] <= end:
            at, channel, note = pending.pop(0)
            clock[0] = at
            backend.inputs['YOUR_KEYBOARD_INPUT'].callback(
                mido.Message('note_on', channel=channel, note=note, velocity=100))
        clock[0] = end
    monkeypatch.setattr(example.time, 'sleep', sleep)
    example.validate_session_controls(music, settings, settings['feedback'])
    return music, backend, settings['feedback']


@pytest.mark.parametrize('note,score', [(60, 1.), (62, -1.)])
def test_rating_flows_through_logicprogym_observations(monkeypatch, tmp_path, note, score):
    task, backend, settings = make_task(monkeypatch, tmp_path, [(.15, 0, note)])
    try:
        obs, _ = task.reset()
        assert task.observation_space.contains(obs)
        reward, obs, _, info = example.play_phrase_and_rate(task, settings, 0)
        assert reward == score
        assert task.observation_space.contains(obs)
        assert 'active_notes' in obs and obs['event_mask'].any()
        event = info['snapshot'].events[0]
        assert event.track_id == 'human' and event.values['note'] == note
        assert event.values['channel'] == 0
        assert event.values['_received_monotonic'] == .15
        output = backend.outputs['YOUR_AGENT_OUTPUT'].messages
        assert [m.note for m in output if m.type == 'note_on'] == [48, 52, 55, 60]
    finally:
        task.close()
    assert all(p.closed for p in (*backend.inputs.values(), *backend.outputs.values()))


def test_playback_wrong_channel_and_unknown_notes_are_not_ratings(monkeypatch, tmp_path):
    task, _, settings = make_task(monkeypatch, tmp_path,
                        [(.03, 0, 60), (.15, 1, 60), (.17, 0, 65)])
    try:
        task.reset()
        reward, _, _, info = example.play_phrase_and_rate(task, settings, 0)
        assert reward is None
        # Rolling observation history does not re-credit events next trial.
        reward, _, _, info = example.play_phrase_and_rate(task, settings, 1)
        assert reward is None
    finally:
        task.close()


def test_first_valid_rating_wins(monkeypatch, tmp_path):
    task, _, settings = make_task(monkeypatch, tmp_path, [(.145, 0, 62), (.146, 0, 60)])
    try:
        task.reset()
        reward, _, _, info = example.play_phrase_and_rate(task, settings, 0)
        assert reward == -1
    finally:
        task.close()


def test_rating_rejects_nonhuman_noteoffs_and_zero_velocity():
    settings = yaml.safe_load(Path('configs/examples/logic_human_feedback.yaml').read_text())['feedback']
    for track, source, kind, velocity in [('agent', EventSource.AGENT, 'note_on', .8),
                                         ('human', EventSource.HUMAN, 'note_off', 0),
                                         ('human', EventSource.HUMAN, 'note_on', 0)]:
        event = DawEvent(0, track, source, kind, {'note': 60, 'velocity': velocity, 'channel': 0})
        assert example.rating(event, settings) is None


def test_training_and_checkpoint_resume_use_observed_ratings(monkeypatch, tmp_path):
    import torch
    task, _, settings = make_task(monkeypatch, tmp_path, [(.15, 0, 60)])
    checkpoint = tmp_path / 'policy.pt'
    argv = ['demo', str(tmp_path / 'feedback.yaml'), '--episodes', '1',
            '--checkpoint', str(checkpoint)]
    monkeypatch.setattr('sys.argv', argv)
    example.main()
    first = torch.load(checkpoint, weights_only=True)
    assert first['updates'] == 1
    assert not torch.equal(first['logits'], torch.zeros(4))
    resumed, _, _ = make_task(monkeypatch, tmp_path, [(.15, 0, 62)])
    monkeypatch.setattr('sys.argv', argv + ['--resume'])
    example.main()
    saved = torch.load(checkpoint, weights_only=True)
    assert saved['updates'] == 2
    assert saved['settings']['track'] == 'human'
    assert saved['session']['config']['tracks'][0]['observe'] == ['notes', 'velocity']


def test_rating_in_final_poll_interval_is_accepted(monkeypatch, tmp_path):
    task, _, settings = make_task(monkeypatch, tmp_path, [(.219, 0, 60)])
    try:
        task.reset()
        reward, _, _, info = example.play_phrase_and_rate(task, settings, 0)
        assert reward == 1
    finally:
        task.close()


def test_unrated_trial_does_not_update_policy(monkeypatch, tmp_path):
    import torch
    task, backend, _ = make_task(monkeypatch, tmp_path)
    checkpoint = tmp_path / 'unrated.pt'
    monkeypatch.setattr('sys.argv', ['demo', str(tmp_path / 'feedback.yaml'),
                                    '--episodes', '1', '--checkpoint', str(checkpoint)])
    example.main()
    saved = torch.load(checkpoint, weights_only=True)
    assert saved['updates'] == 0
    assert torch.equal(saved['logits'], torch.zeros(4))
    assert all(p.closed for p in (*backend.inputs.values(), *backend.outputs.values()))
