"""Tests for converting researcher YAML into typed experiment controls."""

from pathlib import Path

import pytest

from logicprogym.actions.specs import ActionRepresentation
from logicprogym.config import LogicProGymConfig


def test_logic_example_compiles_presets_and_custom_actions():
    """The checked-in example should remain executable documentation."""

    path = Path(__file__).parents[1] / "tests" / "fixtures" / "configs" / "logic_basic.yaml"
    config = LogicProGymConfig.from_yaml(path)

    assert [track.alias for track in config.tracks] == ["human", "agent"]
    assert config.tracks[0].observe == ("notes", "velocity", "controls")
    assert config.actions[-1].id == "agent/brightness"
    assert config.actions[-1].track_id == "agent"
    assert config.actions[-1].representation is ActionRepresentation.CONTINUOUS


def test_discrete_pitch_can_be_declared_without_a_preset(tmp_path):
    """YAML values define the policy categories rather than wire integers."""

    path = tmp_path / "scale.yaml"
    path.write_text(
        """
tracks:
  - alias: lead
    actions:
      - id: pitch
        target: musical.pitch
        representation: discrete
        values: [60, 62, 64, 67]
        encoding:
          unit: midi_note
""",
        encoding="utf-8",
    )
    spec = LogicProGymConfig.from_yaml(path).actions[0]
    assert spec.id == "lead/pitch"
    assert spec.values == (60, 62, 64, 67)
    assert spec.encoding == {"unit": "midi_note"}


def test_duplicate_track_aliases_are_rejected(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("tracks: [{alias: agent}, {alias: agent}]", encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        LogicProGymConfig.from_yaml(path)
