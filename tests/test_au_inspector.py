"""Python contract tests for native Audio Unit inspection profiles."""

import json
from types import SimpleNamespace

import pytest

from logicprogym.instruments.inspector import AudioUnitInspector, AudioUnitProfile


PROFILE = {
    "schemaVersion": 1,
    "inspectedAt": "2026-08-26T12:00:00Z",
    "liveLogicInstance": False,
    "component": {
        "name": "Example: Synth",
        "type": "aumu",
        "subtype": "Syn1",
        "manufacturer": "Acme",
        "version": 65536,
    },
    "parameters": [
        {
            "address": 17,
            "identifier": "filter.cutoff",
            "name": "Filter Cutoff",
            "displayName": "Cutoff",
            "minimum": 20.0,
            "maximum": 20000.0,
            "currentValue": 1000.0,
            "unit": 8,
            "unitName": "Hertz",
            "flags": 3,
            "valueStrings": None,
            "groupPath": ["Filter"],
        }
    ],
    "factoryPresets": [{"number": 0, "name": "Init"}],
    "notes": ["Separate instance"],
}


def test_profile_loader_preserves_parameter_identity_and_limits():
    profile = AudioUnitProfile.from_dict(PROFILE)
    assert profile.live_logic_instance is False
    assert profile.component.subtype == "Syn1"
    assert profile.parameters[0].identifier == "filter.cutoff"
    assert profile.parameters[0].group_path == ("Filter",)
    assert profile.parameters[0].maximum == 20000.0

    control = profile.world_controls("agent_synth", device_id="instrument")[0]
    assert control.id == "agent_synth/instrument/filter.cutoff"
    assert control.track_id == "agent_synth"
    assert control.metadata["au_address"] == 17
    assert control.metadata["source"] == "separate_audio_unit_instance"


def test_python_wrapper_uses_fourcc_arguments_without_a_shell(tmp_path, monkeypatch):
    executable = tmp_path / "inspector"
    executable.touch()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout=json.dumps(PROFILE), stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    profile = AudioUnitInspector(executable).inspect("aumu", "Syn1", "Acme")
    assert captured["command"] == [
        str(executable),
        "inspect",
        "--type",
        "aumu",
        "--subtype",
        "Syn1",
        "--manufacturer",
        "Acme",
        "--compact",
    ]
    assert captured["kwargs"]["check"] is False
    assert profile.parameters[0].name == "Filter Cutoff"


def test_native_failures_become_actionable_python_errors(tmp_path, monkeypatch):
    executable = tmp_path / "inspector"
    executable.touch()
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2, stdout="", stderr="Audio Unit was not found"
        ),
    )
    with pytest.raises(RuntimeError, match="not found"):
        AudioUnitInspector(executable).inspect("aumu", "None", "None")
