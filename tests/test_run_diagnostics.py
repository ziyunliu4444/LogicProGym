"""Run diagnostics are opt-in and tested without opening Logic."""
import hashlib
import json
import gymnasium as gym
import pytest
from logicprogym.timing import StepTiming
from logicprogym.experiments import write_manifest
from logicprogym.env import LogicProEnv
from tests.test_env import DummyAdapter
from tests.test_reset_controls import spec, plan

def test_timing_and_reset_boundary():
    ticks = iter([10., 10.1, 10.5, 10.7, 20., 20.1])
    inner = LogicProEnv(DummyAdapter(), [])
    env = StepTiming(inner, clock=lambda: next(ticks))
    env.reset()
    info = env.step({})[-1]
    assert info['timing']['step_duration_seconds'] == pytest.approx(.1)
    assert info['timing']['start_interval_seconds'] is None
    info = env.step({})[-1]
    assert info['timing']['start_interval_seconds'] == .5
    env.reset()
    assert env.step({})[-1]['timing']['start_interval_seconds'] is None
    env.close()

def test_timing_factory(tmp_path):
    from logicprogym.factory import make
    template = 'adapter: {type: logic_midi, routes: [{track_id: agent, output_port: Test}]}\ntracks: []\nenvironment: {timing: true}\n'
    path = tmp_path / 'session.yaml'
    path.write_text(template)
    env = make(path)
    assert isinstance(env, StepTiming)
    assert not env.unwrapped._connected
    env.close()
    path.write_text(template.replace('true', 'wrong'))
    with pytest.raises(ValueError, match='timing'):
        make(path)

def test_manifest_has_seed_versions_and_checkpoint(tmp_path):
    config = tmp_path / 'session.yaml'
    config.write_text('tracks: []\n')
    checkpoint = tmp_path / 'policy.pt'
    checkpoint.write_bytes(b'test weights')
    output = tmp_path / 'run.json'
    manifest = write_manifest(output, config, seed=42, checkpoint=checkpoint,
                              labels={'logic_project': 'Test project'})
    assert json.loads(output.read_text()) == manifest
    assert manifest['seed'] == 42
    assert manifest['session']['config'] == {'tracks': []}
    assert manifest['dependencies']['gymnasium']
    assert manifest['checkpoint']['sha256'] == hashlib.sha256(b'test weights').hexdigest()
    with pytest.raises(FileExistsError):
        write_manifest(output, config, seed=42)
    assert json.loads(output.read_text()) == manifest

def test_invalid_manifest_leaves_no_file(tmp_path):
    config = tmp_path / 'session.yaml'
    config.write_text('tracks: []')
    output = tmp_path / 'run.json'
    with pytest.raises(FileNotFoundError):
        write_manifest(output, config, seed=1, checkpoint=tmp_path/'missing.pt')
    assert not output.exists()
    with pytest.raises(ValueError):
        write_manifest(output, config, seed=-1)
    assert not output.exists()

def test_reset_releases_agent_gate_then_sustain_without_human_commands():
    import numpy as np
    from logicprogym.actions.specs import ActionSpec, ActionRepresentation, UpdateMode
    gate = ActionSpec('agent/gate', 'agent', 'midi.note_gate',
        ActionRepresentation.BINARY, shape=(128,), update_mode=UpdateMode.HOLD)
    sustain = spec('midi.cc.64')
    adapter = DummyAdapter()
    env = LogicProEnv(adapter, [gate, sustain], reset_controls=plan([0.0]))
    env.reset()
    notes = np.zeros(128, dtype=np.int8)
    notes[60] = 1
    env.step({'agent/gate': notes, 'agent/cutoff': [1.0]})
    adapter.commands.clear()
    env.reset()
    assert [c.kind for c in adapter.commands] == ['midi.note_off', 'midi.cc.64']
    assert all(c.track_id == 'agent' for c in adapter.commands)
    adapter.commands.clear()
    env.reset()
    assert [c.kind for c in adapter.commands] == ['midi.cc.64']
    env.close()
