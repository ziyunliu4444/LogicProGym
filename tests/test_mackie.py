"""Tests for the transport-independent Mackie Control helpers."""

import mido
import pytest

from logicprogym.adapters.mackie import (
    MackieLcd,
    button_messages,
    parse_lcd_update,
    instrument_page,
    track_select_messages,
    vpot_message,
)


def lcd_message(offset: int, text: str) -> mido.Message:
    data = (0, 0, 0x66, 0x14, 0x12, offset, *(ord(character) for character in text))
    return mido.Message("sysex", data=data)


def test_parse_lcd_update() -> None:
    assert parse_lcd_update(lcd_message(56, "Robotic")) == (56, "Robotic")
    assert parse_lcd_update(mido.Message("clock")) is None


def test_lcd_reconstructs_partial_updates_and_strips() -> None:
    lcd = MackieLcd()
    assert lcd.consume(lcd_message(0, "Alchemy"))
    assert lcd.consume(lcd_message(56, "Robotic"))
    assert lcd.rows[0].startswith("Alchemy")
    assert lcd.rows[1].startswith("Robotic")
    assert lcd.strips[0] == ("Alchemy", "Robotic")
    assert not lcd.consume(lcd_message(56, "Robotic"))


def test_instrument_button_has_press_and_release() -> None:
    press, release = button_messages("instrument")
    assert (press.type, press.note, press.velocity) == ("note_on", 0x2D, 0x7F)
    assert (release.type, release.note, release.velocity) == ("note_on", 0x2D, 0)


def test_vpot_uses_relative_mackie_values() -> None:
    assert vpot_message(0, 3).dict()["value"] == 3
    assert vpot_message(7, -2).dict()["value"] == 0x42
    with pytest.raises(ValueError):
        vpot_message(8, 1)
    with pytest.raises(ValueError):
        vpot_message(0, 0)


def test_track_select_uses_current_bank_select_buttons() -> None:
    press, release = track_select_messages(1)
    assert (press.note, press.velocity) == (0x19, 0x7F)
    assert (release.note, release.velocity) == (0x19, 0)
    with pytest.raises(ValueError):
        track_select_messages(8)


def test_instrument_page_is_parsed_from_logic_header() -> None:
    lcd = MackieLcd()
    lcd.apply(0, 'Track 1 "Alchemy" Stereo Page 1/71')
    assert instrument_page(lcd) == (1, 71)
