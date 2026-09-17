import pytest
from dataclasses import replace

from logicprogym.config import LogicProGymConfig
from logicprogym.control_setup import preview, validate_routes


@pytest.mark.parametrize('target', ['midi.cc.128', 'midi.cc.invalid', 'plugin.absolute', 'unknown'])
def test_unsupported_target_rejected(target):
    config = LogicProGymConfig.from_yaml('configs/examples/logic_midi_only.yaml')
    track = next(t for t in config.tracks if t.actions)
    changed = replace(track, actions=(replace(track.actions[0], target=target),))
    config = replace(config, tracks=tuple(changed if t is track else t for t in config.tracks))
    with pytest.raises(ValueError, match='unsupported Logic action target'):
        validate_routes(config)


@pytest.mark.parametrize('file,mode', [
    ('logic_midi_only.yaml', 'instrument: MIDI'),
    ('logic_mackie_only.yaml', 'synth: Mackie'),
    ('logic_human_agent.yaml', 'agent: MIDI + Mackie'),
    ('logic_two_agents.yaml', 'trombone: MIDI'),
])
def test_preview_modes(file, mode):
    assert mode in preview('configs/examples/' + file)


def test_missing_midi_route_rejected():
    config = LogicProGymConfig.from_yaml('configs/examples/logic_midi_only.yaml')
    config.adapter['routes'] = []
    with pytest.raises(ValueError, match='output_port'):
        validate_routes(config)


def test_missing_mackie_assignment_rejected():
    config = LogicProGymConfig.from_yaml('configs/examples/logic_mackie_only.yaml')
    config.adapter['controllers'] = []
    with pytest.raises(ValueError, match='Mackie assignment'):
        validate_routes(config)
