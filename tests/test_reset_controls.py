"""Opt-in initialization is validated before IO and never claims feedback."""
from dataclasses import replace
import pytest
from logicprogym.actions.specs import ActionSpec, ActionRepresentation, UpdateMode
from logicprogym.reset_controls import reset_commands
from logicprogym.env import LogicProEnv
from tests.test_env import DummyAdapter

def spec(target='midi.cc.20'):
    return ActionSpec('agent/cutoff', 'agent', target, ActionRepresentation.CONTINUOUS)

def plan(value=None, **changes):
    entry = {'action': 'agent/cutoff', 'ownership': 'agent',
             'value': [0.5] if value is None else value}
    entry.update(changes)
    return {'enabled': True, 'controls': [entry]}

def test_disabled_by_default():
    assert reset_commands([spec()], None) == []
    assert reset_commands([spec()], {'enabled': False}) == []

@pytest.mark.parametrize('target', ['plugin.relative', 'midi.note_on', 'midi.cc.120'])
def test_reject_unsafe_or_relative_targets(target):
    with pytest.raises(ValueError):
        reset_commands([spec(target)], plan())

@pytest.mark.parametrize('value', [[float('nan')], [2], [0, 1]])
def test_bad_values(value):
    with pytest.raises(ValueError):
        reset_commands([spec()], plan(value))

def test_ownership_unknown_and_duplicates():
    with pytest.raises(ValueError):
        reset_commands([spec()], plan(ownership='shared'))
    with pytest.raises(ValueError):
        reset_commands([replace(spec(), metadata={'ownership': 'human'})], plan())
    with pytest.raises(ValueError):
        reset_commands([spec()], plan(action='human/cutoff'))
    settings = plan()
    settings['controls'] *= 2
    with pytest.raises(ValueError):
        reset_commands([spec()], settings)
    with pytest.raises(ValueError):
        reset_commands([replace(spec(), update_mode=UpdateMode.RELATIVE)], plan())

def test_every_reset_applies_and_reports_unconfirmed():
    adapter = DummyAdapter()
    env = LogicProEnv(adapter, [spec()], reset_controls=plan())
    for _ in range(2):
        observation, info = env.reset()
        assert info['reset_controls']['status'] == 'sent'
        assert info['reset_controls']['confirmed'] is False
    assert len(adapter.commands) == 2
    assert all(c.track_id == 'agent' and c.kind == 'midi.cc.20' for c in adapter.commands)
    env.close()

def test_send_failure_not_reported_as_success():
    class Broken(DummyAdapter):
        def send(self, commands):
            raise OSError('MIDI disconnected')
    env = LogicProEnv(Broken(), [spec()], reset_controls=plan())
    with pytest.raises(OSError, match='disconnected'):
        env.reset()

def test_yaml_constructor(tmp_path):
    from logicprogym.factory import make
    path = tmp_path / 'session.yaml'
    path.write_text("""adapter:
  type: logic_midi
  routes:
    - {track_id: agent, output_port: Test, channel: 0}
environment:
  reset_controls:
    enabled: true
    controls:
      - {action: agent/bend, ownership: agent, value: [0.0]}
tracks:
  - alias: agent
    actions:
      - {id: bend, target: midi.pitch_bend, representation: continuous, range: [-1, 1]}
""")
    env = make(path)
    assert env._reset_commands[0].kind == 'midi.pitch_bend'
    assert not env._connected
    env.close()
