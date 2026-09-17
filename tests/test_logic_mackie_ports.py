"""Offline checks for naming and rendering virtual Mackie endpoint messages."""

import mido
import yaml

from tests.fixtures.legacy.logic_mackie_ports import FROM_LOGIC, TO_LOGIC, format_message
from tests.fixtures.legacy.logic_mackie_emulator import (
    endpoint_names,
    load_controller_count,
    load_target_tracks,
    save_target_tracks,
    is_instrument_edit,
)


def test_virtual_endpoint_names_are_directionally_explicit():
    assert TO_LOGIC == "LogicProGym Control To Logic"
    assert FROM_LOGIC == "LogicProGym Control From Logic"


def test_raw_monitor_keeps_semantics_and_exact_bytes():
    rendered = format_message(mido.Message("control_change", channel=0, control=16, value=65))
    assert "control_change" in rendered
    assert "B0 10 41" in rendered


def test_multiple_controller_endpoint_names_are_unique():
    assert endpoint_names(TO_LOGIC, 2) == [
        "LogicProGym Control 1 To Logic",
        "LogicProGym Control 2 To Logic",
    ]
    assert endpoint_names(FROM_LOGIC, 2) == [
        "LogicProGym Control 1 From Logic",
        "LogicProGym Control 2 From Logic",
    ]


def test_controller_track_assignments_survive_restart(tmp_path):
    state_file = tmp_path / "mackie.yaml"
    save_target_tracks(state_file, [0, 1])
    assert load_target_tracks(state_file, controllers=2) == [0, 1]
    saved = yaml.safe_load(state_file.read_text())
    assert saved["controller_count"] == 2
    assert saved["controllers"] == [
        {"controller": 1, "id": "track_1", "track": 1},
        {"controller": 2, "id": "track_2", "track": 2},
    ]
    assert load_controller_count(state_file) == 2


def test_instrument_edit_header_is_distinct_from_select_view():
    from logicprogym.adapters.mackie import MackieLcd

    lcd = MackieLcd()
    lcd.apply(0, "Track 2 Synth Page 1/8")
    assert is_instrument_edit(lcd)
    selection = MackieLcd()
    selection.apply(0, "Select Synth Page 1/8")
    assert not is_instrument_edit(selection)
