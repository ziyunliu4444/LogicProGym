"""Public discovery and template checks; never access MIDI hardware."""

import json
from pathlib import Path
import subprocess

import gymnasium as gym
import yaml

from logicprogym import cli


def test_devices_json_preserves_exact_names(monkeypatch, capsys):
    monkeypatch.setattr(cli, '_ports', lambda: (['My Keyboard Port'], ['My Agent Bus']))
    assert cli.devices(True) == 0
    assert json.loads(capsys.readouterr().out) == {
        'inputs': ['My Keyboard Port'], 'outputs': ['My Agent Bus']}


def test_devices_empty_and_failure(monkeypatch, capsys):
    monkeypatch.setattr(cli, '_ports', lambda: ([], []))
    assert cli.devices() == 0
    assert '(none found)' in capsys.readouterr().out

    def unavailable():
        raise subprocess.TimeoutExpired('probe', 10)

    monkeypatch.setattr(cli, '_ports', unavailable)
    assert cli.devices(True) == 1
    assert 'error' in json.loads(capsys.readouterr().out)


def test_public_templates_have_no_personal_devices():
    def check_ports(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('input_port', 'output_port') and item is not None:
                    assert item.startswith('YOUR_'), item
                check_ports(item)
        elif isinstance(value, list):
            for item in value:
                check_ports(item)

    for path in Path('configs/examples').glob('*.yaml'):
        check_ports(yaml.safe_load(path.read_text()))


def test_release_environment_alias():
    env = gym.make('LogicProGym/Logic-v0',
                   config_path='configs/examples/logic_midi_only.yaml')
    assert env.action_space is not None
    env.close()  # Do not reset: this test never opens devices.
