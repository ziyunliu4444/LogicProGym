"""Small, DAW-independent building blocks for Mackie Control emulation.

The module deliberately contains no MIDI-port code.  It translates Mackie
messages and maintains the controller display, while an adapter decides how
messages are transported to and from a DAW.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

import mido


MACKIE_MANUFACTURER = (0x00, 0x00, 0x66)
MACKIE_CONTROL_DEVICE = 0x14
LCD_UPDATE = 0x12
LCD_COLUMNS = 56
LCD_ROWS = 2
SCRIBBLE_STRIPS = 8
STRIP_WIDTH = 7

# Mackie Control button note numbers used during instrument exploration.
BUTTON_NOTES = {
    "track": 0x28,
    "send": 0x29,
    "pan": 0x2A,
    "plugin": 0x2B,
    "eq": 0x2C,
    "instrument": 0x2D,
    "cursor_up": 0x60,
    "cursor_down": 0x61,
    "cursor_left": 0x62,
    "cursor_right": 0x63,
    "zoom": 0x64,
    "name_value": 0x34,
}


def button_messages(name: str) -> tuple[mido.Message, mido.Message]:
    """Return a complete press/release pair for a Mackie button."""

    try:
        note = BUTTON_NOTES[name]
    except KeyError as error:
        choices = ", ".join(sorted(BUTTON_NOTES))
        raise ValueError(f"Unknown Mackie button {name!r}; choose from {choices}") from error
    return (
        mido.Message("note_on", channel=0, note=note, velocity=0x7F),
        mido.Message("note_on", channel=0, note=note, velocity=0),
    )


def track_select_messages(index: int) -> tuple[mido.Message, mido.Message]:
    """Return a press/release pair for a track Select button in the current bank."""

    if not 0 <= index < SCRIBBLE_STRIPS:
        raise ValueError("Track index must be between 0 and 7")
    note = 0x18 + index
    return (
        mido.Message("note_on", channel=0, note=note, velocity=0x7F),
        mido.Message("note_on", channel=0, note=note, velocity=0),
    )


def vpot_message(index: int, steps: int) -> mido.Message:
    """Encode a relative turn of one of the eight Mackie V-Pots.

    Positive values turn clockwise and negative values counter-clockwise.
    One MIDI message can represent at most 63 relative steps.
    """

    if not 0 <= index < SCRIBBLE_STRIPS:
        raise ValueError("V-Pot index must be between 0 and 7")
    if steps == 0 or not -63 <= steps <= 63:
        raise ValueError("V-Pot steps must be in -63..-1 or 1..63")
    value = steps if steps > 0 else 0x40 + abs(steps)
    return mido.Message("control_change", channel=0, control=0x10 + index, value=value)


def parse_lcd_update(message: mido.Message) -> tuple[int, str] | None:
    """Decode an MCU LCD SysEx message into ``(offset, text)``."""

    if message.type != "sysex":
        return None
    data = tuple(message.data)
    header = (*MACKIE_MANUFACTURER, MACKIE_CONTROL_DEVICE, LCD_UPDATE)
    if len(data) < len(header) + 1 or data[: len(header)] != header:
        return None
    offset = data[len(header)]
    text = "".join(chr(byte) if 0x20 <= byte <= 0x7E else " " for byte in data[len(header) + 1 :])
    return offset, text


@dataclass
class MackieLcd:
    """Reconstruct the Mackie two-row, 56-column character display."""

    cells: list[str] = field(default_factory=lambda: [" "] * (LCD_COLUMNS * LCD_ROWS))

    def apply(self, offset: int, text: str) -> bool:
        """Apply a partial display update and report whether anything changed."""

        changed = False
        for position, character in enumerate(text, start=offset):
            if position >= len(self.cells):
                break
            if self.cells[position] != character:
                self.cells[position] = character
                changed = True
        return changed

    def consume(self, message: mido.Message) -> bool:
        """Apply an LCD message, returning false for unrelated messages."""

        update = parse_lcd_update(message)
        if update is None:
            return False
        return self.apply(*update)

    @property
    def rows(self) -> tuple[str, str]:
        """Return the complete upper and lower display rows."""

        text = "".join(self.cells)
        return text[:LCD_COLUMNS], text[LCD_COLUMNS:]

    @property
    def strips(self) -> tuple[tuple[str, str], ...]:
        """Return the upper/lower seven-character text for each V-Pot."""

        upper, lower = self.rows
        return tuple(
            (
                upper[index * STRIP_WIDTH : (index + 1) * STRIP_WIDTH].strip(),
                lower[index * STRIP_WIDTH : (index + 1) * STRIP_WIDTH].strip(),
            )
            for index in range(SCRIBBLE_STRIPS)
        )

    def format(self) -> str:
        """Create a compact table suitable for an interactive terminal."""

        border = "+" + "+".join("-" * STRIP_WIDTH for _ in range(SCRIBBLE_STRIPS)) + "+"
        lines = [border]
        for row in self.rows:
            chunks = [row[i : i + STRIP_WIDTH] for i in range(0, LCD_COLUMNS, STRIP_WIDTH)]
            lines.append("|" + "|".join(chunks) + "|")
        lines.append(border)
        return "\n".join(lines)


def send_all(port, messages: Iterable[mido.Message]) -> None:
    """Send a sequence of MIDI messages through a Mido output port."""

    for message in messages:
        port.send(message)


def instrument_page(lcd: MackieLcd) -> tuple[int, int] | None:
    """Extract Logic's ``Page current/total`` marker from an LCD snapshot."""

    match = re.search(r"Page\s*(\d+)\s*/\s*(\d+)", lcd.rows[0], re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def instrument_header(lcd: MackieLcd) -> dict | None:
    """Parse the whole header row, not its artificial seven-character cells.

    Quotes delimit track/preset and instrument names. A long instrument name
    may leave no visible page number; never infer a number from its text.
    """
    row = lcd.rows[0].strip()
    match = re.match(r'Track\s+(\d+)\b', row, re.IGNORECASE)
    if match is None:
        return None
    names = re.findall(r'"([^\"]*)"', row[match.end():])
    page = instrument_page(lcd)
    if page is None and len(names) < 2:
        return None
    return {'track': int(match[1]), 'track_name': names[0] if names else None,
            'instrument_name': names[1] if len(names) > 1 else None, 'page': page}
