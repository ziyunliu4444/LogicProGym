"""Tests for reusable live Logic setup helpers."""

from types import SimpleNamespace

import yaml

from logicprogym.adapters.mackie import MackieLcd
from logicprogym.adapters.mackie import instrument_header
from logicprogym.logic_setup import is_parameter_view, save_catalog, _scan_header


def test_scan_requires_requested_track_header_not_mixer_or_other_track():
    controller = SimpleNamespace(lcd=MackieLcd())
    controller.lcd.apply(0, 'StGrPn 8-BitM Trmbns')
    controller.lcd.apply(56, '0      0      0')
    assert not _scan_header(controller, 3)
    controller.lcd = MackieLcd()
    controller.lcd.apply(0, 'Track 2 Alchemy Page 1/71')
    assert not _scan_header(controller, 3)
    controller.lcd = MackieLcd()
    controller.lcd.apply(0, 'Track 3 Trombone Page 1/4')
    assert _scan_header(controller, 3)


def test_long_quoted_header_preserves_names_without_inventing_page():
    lcd = MackieLcd()
    lcd.apply(0, 'Track 3 "Trombones" "Sampler (Multi-Sample) Stereo" Pag ')
    header = instrument_header(lcd)
    assert header['track_name'] == 'Trombones'
    assert header['instrument_name'] == 'Sampler (Multi-Sample) Stereo'
    assert header['page'] is None
    assert _scan_header(SimpleNamespace(lcd=lcd), 3)


def test_parameter_view_accepts_header_or_configured_parameter_names() -> None:
    header = SimpleNamespace(lcd=MackieLcd())
    header.lcd.apply(0, "Track 2 Synth Page 1/8")
    assert is_parameter_view(header)

    values = SimpleNamespace(lcd=MackieLcd())
    values.lcd.apply(0, "Robotc Cutoff")
    assert is_parameter_view(values, {"Cutoff"})
    assert not is_parameter_view(values, {"Volume"})

    later_page = SimpleNamespace(lcd=MackieLcd())
    later_page.lcd.apply(0, "Pu/Pu2 Degrad LFORat LFO Md Attack Decay  Sus    Rel    ")
    later_page.lcd.apply(56, "49.60% 0.0 %  1/8*   23.20% 0.80 % 0.0 %  100.00 34.90% ")
    assert is_parameter_view(later_page, {"Cutoff"})


def test_catalog_writer_creates_reusable_track_mapping(tmp_path) -> None:
    path = tmp_path / "catalog.yaml"
    save_catalog(
        path,
        track_id="agent",
        logic_track=2,
        controller=2,
        pages=[{"page": 1, "parameters": [{"slot": 2, "name": "Cutoff"}]}],
    )
    saved = yaml.safe_load(path.read_text())
    assert saved["tracks"]["agent"]["logic_track"] == 2
    assert saved["tracks"]["agent"]["pages"][0]["parameters"][0] == {
        "slot": 2,
        "name": "Cutoff",
    }
