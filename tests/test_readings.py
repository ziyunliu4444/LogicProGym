from dataclasses import FrozenInstanceError

import pytest

import logicprogym
from logicprogym.models import DawSnapshot


@pytest.mark.parametrize('hybrid', [False, True])
def test_public_readings_preserve_raw_age_and_numeric_validity(hybrid):
    feedback = {'parameter_readings': {
        'cutoff': {'name': 'Cutoff', 'display_raw': '60 %', 'display_age_seconds': 3.,
                   'value': .6, 'valid': False},
        'res': {'name': 'Res', 'raw': '20 %', 'age_seconds': .1,
                'value': .2, 'valid': True},
        'arp': {'name': 'Arp Md', 'display_raw': 'Off', 'valid': False},
        'missing': {'name': 'Thin', 'valid': False},
    }}
    info = {'snapshot': DawSnapshot(diagnostics={'mackie': feedback} if hybrid else feedback)}
    readings = logicprogym.parameter_readings(info)
    assert readings['cutoff'].raw == '60 %'
    assert readings['cutoff'].age_seconds == 3.
    assert readings['cutoff'].value is None
    assert not readings['cutoff'].valid
    assert readings['res'].value == .2
    assert readings['res'].valid
    assert readings['arp'].raw == 'Off'
    assert readings['missing'].raw is None
    with pytest.raises(FrozenInstanceError):
        readings['cutoff'].raw = 'changed'
    feedback['parameter_readings']['cutoff']['display_raw'] = 'new'
    assert readings['cutoff'].raw == '60 %'


def test_missing_feedback_is_empty():
    assert logicprogym.parameter_readings({}) == {}
    assert logicprogym.parameter_readings({'snapshot': DawSnapshot()}) == {}
