"""Checkpoint provenance must catch session changes without accessing MIDI."""

import pytest
from logicprogym.checkpoints import session_metadata, validate_session


def test_resume_checks_configuration_not_path(tmp_path):
    first = tmp_path / 'first.yaml'
    second = tmp_path / 'second.yaml'
    first.write_text('tracks: []\n')
    second.write_text('tracks: []\n')
    saved = {'session': session_metadata(first)}
    validate_session(saved, session_metadata(second))
    second.write_text('tracks: [changed]\n')
    with pytest.raises(ValueError, match='configuration differs'):
        validate_session(saved, session_metadata(second))
    with pytest.raises(ValueError, match='metadata'):
        validate_session({}, session_metadata(first))
