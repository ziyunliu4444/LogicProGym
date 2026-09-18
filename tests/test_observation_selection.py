"""Observation routing contracts; all adapters/clocks are in-memory."""
from dataclasses import replace

import numpy as np
import pytest

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv
from logicprogym.frames import FrameClock
from logicprogym.models import DawEvent, DawSnapshot, EventSource, ParameterDescriptor, TrackDescriptor, TransportState


class SelectionAdapter(LogicProAdapter):
    capabilities = AdapterCapabilities(human_events=True, plugin_parameters=True,
                                       transport_read=True, agent_output=True)

    def __init__(self):
        self.snapshot = DawSnapshot()
        self.connected = False
        self.commands = []

    def connect(self):
        self.connected = True

    def discover(self):
        # IDs deliberately do not encode ownership.
        return ([TrackDescriptor(x, x) for x in ('human', 'agent', 'hidden')],
                [ParameterDescriptor('unrelated-id', 'agent', 'Cutoff'),
                 ParameterDescriptor('agent-looking-id', 'hidden', 'Secret')])

    def receive(self):
        result, self.snapshot = self.snapshot, DawSnapshot()
        return result

    def send(self, commands):
        self.commands.extend(commands)

    def close(self):
        self.connected = False


def event(track='human', kind='note_on', **values):
    return DawEvent(123, track, EventSource.HUMAN, kind, values)


def mixed_snapshot():
    return DawSnapshot(
        transport=TransportState(sample_position=1234, tempo=99, playing=True),
        events=(event(note=60, velocity=.8, secret='not a supported field'),
                event('agent', note=70, velocity=.9),
                event('hidden', note=80, velocity=.7),
                event(kind='control', control=20, value=.25),
                event(kind='pitch', value=.1),
                event('agent', 'parameter', parameter_id='unrelated-id', value=.4),
                event('hidden', 'parameter', parameter_id='agent-looking-id', value=.9)),
        parameter_values={'unrelated-id': .4, 'agent-looking-id': .9, 'undiscovered': .2},
        diagnostics={'midi': {'queued_events': 7, 'frame_queue_dropped': 0,
                              'clock_source': 'local', 'hidden_notes': [80]},
                     'mackie': {'parameter_readings': {
                         'unrelated-id': {'raw': '40%', 'valid': True, 'extra': 'secret'},
                         'agent-looking-id': {'raw': '90%', 'valid': True}},
                         'mackie_displays': {'agent': 'unverified text'},
                         'mackie_pages': {'hidden': 10}},
                     'arbitrary': 'secret'})


def test_reset_steps_history_info_reward_and_masks_are_selected():
    backend = SelectionAdapter()
    original = mixed_snapshot()
    backend.snapshot = original
    rewarded = []
    env = LogicProEnv(backend, [], track_observations={
        'human': ['notes'], 'agent': ['plugin_parameters']},
        reward=lambda snapshot, action: rewarded.append(snapshot) or 0)
    try:
        obs, info = env.reset()
        assert env.observation_space.contains(obs)
        assert obs['active_notes'][0, 60, 0] == 1
        assert obs['active_notes'][0, 60, 1] == 0
        assert not obs['active_notes'][1:].any()
        np.testing.assert_array_equal(obs['track_mask'][:3], [1, 1, 0])
        np.testing.assert_array_equal(obs['parameter_mask'][:2], [1, 0])
        np.testing.assert_array_equal(obs['parameter_valid'][:2], [1, 0])
        assert obs['parameter_values'][0] == pytest.approx(.4)
        assert obs['parameter_values'][1] == 0
        selected = info['snapshot']
        assert [(e.track_id, e.kind) for e in selected.events] == [('human', 'note_on'), ('agent', 'parameter')]
        assert selected.events[0].values == {'note': 60, 'velocity': 0.0}
        assert selected.transport == TransportState()
        assert set(selected.parameter_values) == {'unrelated-id'}
        assert selected.diagnostics['mackie'] == {'parameter_readings': {
            'unrelated-id': {'raw': '40%', 'valid': True}}}
        assert 'hidden_notes' not in selected.diagnostics['midi']
        assert 'arbitrary' not in selected.diagnostics
        # Public filtering must not modify the backend's snapshot.
        assert original.events[0].values['velocity'] == .8
        assert original.diagnostics['mackie']['mackie_displays']
        backend.snapshot = DawSnapshot(events=(event('hidden', note=90, velocity=.3),))
        obs, _, _, _, info = env.step({})
        assert rewarded[-1] is info['snapshot']
        assert not rewarded[-1].events
        assert obs['event_mask'].sum() == 2  # Only selected history persists.
        assert not obs['active_notes'][2].any()
        backend.snapshot = DawSnapshot(events=(event(kind='note_off', note=60, velocity=.4),))
        obs, *_ = env.step({})
        assert not obs['active_notes'].any()
        obs, info = env.reset()
        assert not obs['event_mask'].any()
        assert not obs['active_notes'].any()
    finally:
        env.close()


def test_controls_only_and_velocity_with_notes():
    backend = SelectionAdapter()
    env = LogicProEnv(backend, [], track_observations={
        'human': ['controls'], 'agent': ['notes', 'velocity'], 'hidden': []})
    backend.snapshot = mixed_snapshot()
    try:
        obs, info = env.reset()
        assert not obs['active_notes'][0].any()
        assert obs['active_notes'][1, 70, 1] == pytest.approx(.9)
        assert {e.kind for e in info['snapshot'].events} == {'control', 'pitch', 'note_on'}
        assert not obs['parameter_mask'].any()
        assert not obs['parameter_valid'].any()
    finally:
        env.close()


def test_frame_selection_precedes_pending_and_skipped_note_state():
    backend = SelectionAdapter()
    now = [0.0]
    clock = FrameClock(.05, clock=lambda: now[0], sleeper=lambda n: now.__setitem__(0, now[0] + n))
    env = LogicProEnv(backend, [], track_observations={'human': ['notes']})
    env.frame_clock = clock
    try:
        env.reset()
        backend.snapshot = DawSnapshot(events=(
            event(note=60, velocity=.8, _received_monotonic=.02),
            event('hidden', note=80, velocity=.9, _received_monotonic=.07),
            event(kind='note_off', note=60, velocity=.3, _received_monotonic=.07)))
        obs, _, _, _, info = env.step({})
        assert info['frame']['midi_events'] == 1
        assert obs['active_notes'][0, 60, 0] == 1
        assert obs['active_notes'][0, 60, 1] == 0
        assert len(clock.pending) == 1
        assert clock.pending[0].values['velocity'] == 0
        now[0] = .18  # The pending release falls in a skipped interval.
        obs, _, _, _, info = env.step({})
        assert info['frame']['skipped_interval_events'] == 1
        assert not obs['active_notes'].any()
        assert not obs['event_mask'].any()
        backend.snapshot = DawSnapshot(events=(event(note=62, velocity=.9, _received_monotonic=1),))
        env.step({})
        assert clock.pending
        env.reset()
        assert not clock.pending
    finally:
        env.close()


@pytest.mark.parametrize('observe', ['[unknown]', 'notes', 'null', '[velocity]', '[17]', '[audio]'])
def test_invalid_yaml_observe_is_rejected(tmp_path, observe):
    path = tmp_path / 'invalid.yaml'
    path.write_text(f'tracks: [{{alias: human, observe: {observe}}}]')
    with pytest.raises(ValueError):
        LogicProGymConfig.from_yaml(path)


def test_yaml_omitted_selection_hides_data_and_actions_still_work(tmp_path):
    path = tmp_path / 'session.yaml'
    path.write_text('tracks: [{alias: agent, actions: {preset: notes_only}}]')
    backend = SelectionAdapter()
    env = LogicProEnv.from_config(backend, LogicProGymConfig.from_yaml(path))
    backend.snapshot = mixed_snapshot()
    try:
        obs, info = env.reset()
        assert not obs['track_mask'].any()
        assert not obs['event_mask'].any()
        assert not info['snapshot'].events
        action = {'agent/note_gate': np.zeros(128, dtype=np.int8),
                  'agent/velocity': np.full(128, .6, dtype=np.float32)}
        action['agent/note_gate'][60] = 1
        env.step(action)
        assert any(c.kind == 'midi.note_on' for c in backend.commands)
    finally:
        env.close()


def test_explicit_transport_and_legacy_python_constructor():
    for selection in (None, {'human': ['transport']}):
        backend = SelectionAdapter()
        backend.snapshot = replace(mixed_snapshot(), parameter_values={'unrelated-id': .4})
        env = LogicProEnv(backend, [], track_observations=selection)
        try:
            obs, info = env.reset()
            assert info['snapshot'].transport.tempo == 99
            assert env.observation_space.contains(obs)
            if selection is None:
                assert len(info['snapshot'].events) == 7
                assert obs['active_notes'][2, 80, 0] == 1
            else:
                assert not info['snapshot'].events
        finally:
            env.close()


def test_observe_only_plugin_requires_capability():
    backend = SelectionAdapter()
    backend.capabilities = replace(backend.capabilities, plugin_parameters=False)
    with pytest.raises(ValueError, match='plugin_parameters'):
        LogicProEnv(backend, [], track_observations={'agent': ['plugin_parameters']})


def test_hidden_events_do_not_consume_history_capacity_and_zero_velocity_releases():
    backend = SelectionAdapter()
    env = LogicProEnv(backend, [], event_capacity=1,
                      track_observations={'human': ['notes']})
    backend.snapshot = DawSnapshot(events=(
        event(note=60, velocity=.5),
        *[event('hidden', note=80, velocity=.8) for _ in range(20)]))
    try:
        obs, info = env.reset()
        assert obs['events'][0, 4] == 60
        assert obs['active_notes'][0, 60, 0] == 1
        backend.snapshot = DawSnapshot(events=(event(note=60, velocity=0),))
        obs, _, _, _, info = env.step({})
        assert info['snapshot'].events[0].kind == 'note_off'
        assert not obs['active_notes'].any()
    finally:
        env.close()


def test_filtered_environment_passes_gymnasium_checker():
    from gymnasium.utils.env_checker import check_env
    from logicprogym.actions.presets import notes_only
    env = LogicProEnv(SelectionAdapter(), notes_only('agent'),
                      track_observations={'human': ['notes'], 'agent': []})
    try:
        check_env(env, skip_render_check=True)
    finally:
        env.close()
