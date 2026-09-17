"""Conservative numeric observations from asynchronous Mackie LCD updates."""

import re
from threading import RLock
from time import monotonic

from logicprogym.adapters.mackie import instrument_header, parse_lcd_update


class MackieFeedback:
    """Accept complete refreshed name/value cells under an observed track header.

    MCU carries no command acknowledgements. These checks establish display
    identity and age, not a causal acknowledgement of a particular action.
    """

    def __init__(self, bindings, clock=monotonic, max_age=2.0):
        self.bindings = bindings
        self.clock = clock
        self.max_age = max_age
        self.context = {}
        self.touched = {}
        self.readings = {}
        self.lock = RLock()

    def invalidate(self):
        """Require a new observed header after selection or parameter commands."""
        with self.lock:
            self.context.clear()
            self.touched.clear()
            self.readings.clear()

    def ingest(self, number, lcd, message):
        update = parse_lcd_update(message)
        if update is None:
            return
        offset, text = update
        now = self.clock()
        with self.lock:
            touched = self.touched.setdefault(number, set())
            updated = set(range(max(0, offset), min(112, offset + len(text))))
            touched.update(updated)
            for binding in self.bindings:
                start = (binding['slot'] - 1) * 7
                cells = set(range(start, start + 7)) | set(range(56 + start, 63 + start))
                if binding['controller'] == number and cells & updated:
                    self.readings.pop(binding['id'], None)
            header = instrument_header(lcd)
            if header and header.get('page') is not None and set(range(56)) <= touched:
                context = (header['track'], header['page'][0])
                self.context[number] = context
                touched.clear()
                return
            if set(range(56)) <= updated and not any(
                b['controller'] == number and
                lcd.strips[b['slot'] - 1][0].casefold() == b['name'].casefold()
                for b in self.bindings
            ):
                self.context.pop(number, None)
                touched.clear()
                return
            context = self.context.get(number)
            if context is None:
                return
            for binding in self.bindings:
                if (binding['controller'] != number or
                        context != (binding['track'], binding['page'])):
                    continue
                start = (binding['slot'] - 1) * 7
                required = set(range(start, start + 7)) | set(range(56 + start, 63 + start))
                if not required <= touched:
                    continue
                name, raw = lcd.strips[binding['slot'] - 1]
                if name.casefold() != binding['name'].casefold():
                    self.readings.pop(binding['id'], None)
                    continue
                # Percentages have a defined normalized range. Bare numbers
                # retain displayed units; enum labels and tempo fractions don't.
                match = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*(%)?', raw.strip())
                if match is None:
                    self.readings.pop(binding['id'], None)
                    continue
                value = float(match[1]) / (100 if match[2] else 1)
                if abs(value) > 3.4e38:
                    continue
                self.readings[binding['id']] = dict(
                    name=name, raw=raw, value=value, received_at=now,
                    unit='normalized_percent' if match[2] else 'display_number',
                    controller=number, track=binding['track'], page=binding['page'],
                    slot=binding['slot'])
                touched.difference_update(required)

    def snapshot(self):
        """Return current readings and age diagnostics without replaying stale data."""
        with self.lock:
            now = self.clock()
            details = {}
            values = {}
            for binding in self.bindings:
                reading = self.readings.get(binding['id'])
                detail = dict(name=binding['name'], valid=False, age_seconds=None)
                if reading:
                    age = max(0.0, now - reading['received_at'])
                    valid = age <= self.max_age and self.context.get(reading['controller']) == (reading['track'], reading['page'])
                    detail.update(reading, age_seconds=age, valid=valid)
                    if valid:
                        values[binding['id']] = reading['value']
                details[binding['id']] = detail
            return values, details
