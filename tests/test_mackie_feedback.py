"""Exercise real LCD fragment parsing without sending MIDI to Logic."""

import mido
import pytest
from logicprogym.adapters.mackie import MackieLcd
from logicprogym.adapters.mackie_feedback import MackieFeedback


def fixture():
    clock = [0.0]
    tracker = MackieFeedback([dict(id='cutoff', name='Cutoff', controller=2,
                                  track=2, page=1, slot=2)], clock=lambda: clock[0])
    lcd = MackieLcd()

    def update(offset, text):
        message = mido.Message('sysex', data=[0, 0, 102, 20, 18, offset, *map(ord, text)])
        lcd.consume(message)
        tracker.ingest(2, lcd, message)

    return tracker, clock, update


def test_raw_feedback_survives_display_replacement_and_actions_but_not_reset():
    tracker, clock, update = fixture()
    update(7, 'Cutoff ')
    update(63, '41.3')
    update(67, '4 %')
    clock[0] = 1
    update(0, 'Track 2 "Synth" "Alchemy" Page 1/71'.ljust(56))
    update(56, 'Robotc Cutoff '.ljust(56))
    tracker.invalidate()  # A new action must not erase historical raw text.
    clock[0] = 4
    values, details = tracker.snapshot()
    assert values == {}
    assert details['cutoff']['display_raw'] == '41.34 %'
    assert details['cutoff']['display_age_seconds'] == 4
    assert not details['cutoff']['valid']
    update(7, 'Cutoff ')  # Name update alone must not refresh old lower text.
    assert tracker.snapshot()[1]['cutoff']['display_age_seconds'] == 4
    update(63, '1/16   ')
    assert tracker.snapshot()[1]['cutoff']['display_raw'] == '1/16'
    assert tracker.snapshot()[1]['cutoff']['display_age_seconds'] == 0
    assert tracker.snapshot()[0] == {}
    tracker.invalidate(clear_raw=True)
    assert 'display_raw' not in tracker.snapshot()[1]['cutoff']



def test_overview_slot_supports_different_value_label_and_clears_on_page_change():
    clock = [0.0]
    tracker = MackieFeedback([dict(id='robot', name='Robotc', controller=1,
                                  track=1, page=1, slot=1)], clock=lambda: clock[0])
    lcd = MackieLcd()

    def update(offset, text):
        message = mido.Message('sysex', data=[0, 0, 102, 20, 18, offset, *map(ord, text)])
        lcd.consume(message)
        tracker.ingest(1, lcd, message)

    update(0, 'Track 1 "8-Bit Memories" "Alchemy Stereo" Page 1/71'.ljust(56))
    update(56, 'Robotc Cutoff Arp Md Thin   Porto  Res    ArpRat ArpOct ')
    assert 'display_raw' not in tracker.snapshot()[1]['robot']
    tracker.invalidate()  # Actions invalidate numeric checks, not learned raw slots.
    update(0, 'Robotic')
    update(56, '19.5')
    assert tracker.snapshot()[0] == {}  # Require all seven value-cell characters.
    update(60, '1 %')
    values, readings = tracker.snapshot()
    assert readings['robot']['display_raw'] == '19.51 %'
    assert readings['robot']['display_name'] == 'Robotic'
    assert readings['robot']['valid']
    assert values['robot'] == pytest.approx(.1951)
    clock[0] = 3.0
    assert tracker.snapshot()[0] == {}
    assert not tracker.snapshot()[1]['robot']['valid']
    update(0, 'Track 1 "8-Bit Memories" "Alchemy Stereo" Page 2/71'.ljust(56))
    update(0, 'Another')
    update(56, '90.00 %')
    assert tracker.snapshot()[1]['robot']['display_raw'] == '19.51 %'
    assert tracker.snapshot()[0] == {}
    tracker.invalidate(clear_raw=True)
    assert not tracker.raw_slots


@pytest.mark.parametrize('slot,name,raw,value', [
    (6, 'Res', '0.78 %', .0078), (8, 'ArpOct', '9.02 %', .0902),
])
def test_numeric_reading_survives_name_update_and_accepts_delta_after_action(slot, name, raw, value):
    clock = [0.0]
    tracker = MackieFeedback([dict(id='p', name=name, controller=1,
                                  track=1, page=1, slot=slot)], clock=lambda: clock[0])
    lcd = MackieLcd()
    def update(offset, text):
        message = mido.Message('sysex', data=[0, 0, 102, 20, 18, offset, *map(ord, text)])
        lcd.consume(message)
        tracker.ingest(1, lcd, message)
    start = (slot - 1) * 7
    update(0, 'Track 1 "Alchemy" Page 1/71'.ljust(56))
    update(56 + start, name.ljust(7))
    update(start, name.ljust(7))
    update(56 + start, raw.ljust(7))
    assert tracker.snapshot()[0]['p'] == pytest.approx(value)
    clock[0] = 1.0
    update(start, name.ljust(7))  # A repeated name must not erase the number.
    assert tracker.snapshot()[0]['p'] == pytest.approx(value)
    assert tracker.snapshot()[1]['p']['age_seconds'] == 1.0
    clock[0] = 3.0
    assert tracker.snapshot()[0] == {}  # Name updates do not extend freshness.
    tracker.invalidate()
    assert tracker.snapshot()[0] == {}
    update(56 + start, '1')  # Only the changed character is sent by Logic.
    assert tracker.snapshot()[0]['p'] == pytest.approx(float('1' + raw[1:-1].strip()) / 100)
    update(56 + start, '-'.ljust(7))
    assert tracker.snapshot()[0] == {}
    assert 'p' not in tracker.numeric_baselines
    tracker.invalidate(clear_raw=True)
    update(start, name.ljust(7))
    update(56 + start, '1')
    assert tracker.snapshot()[0] == {}  # No delta reconstruction across reset.


def test_fragment_identity_age_and_invalidation():
    tracker, clock, update = fixture()
    update(0, 'Track 2 "Synth" "Alchemy" Page 1/71'.ljust(56))
    update(7, 'Cutoff ')
    update(63, '41.3')
    assert tracker.snapshot()[0] == {}
    update(67, '4 %')
    assert tracker.snapshot()[0]['cutoff'] == pytest.approx(.4134)
    assert tracker.snapshot()[1]['cutoff']['raw'] == '41.34 %'
    clock[0] = 3
    assert tracker.snapshot()[0] == {}
    assert not tracker.snapshot()[1]['cutoff']['valid']
    tracker.invalidate()
    update(7, 'Cutoff ')
    update(63, '50.00 %')
    assert tracker.snapshot()[0] == {}  # Requires a new observed header.


@pytest.mark.parametrize('track,page,name,raw', [
    (3, 1, 'Cutoff ', '41.34 %'), (2, 2, 'Cutoff ', '41.34 %'),
    (2, 1, 'Robotc ', '41.34 %'), (2, 1, 'Cutoff ', '1/16   '),
])
def test_wrong_identity_and_nonnumeric_readings_are_unavailable(track, page, name, raw):
    tracker, _, update = fixture()
    update(0, f'Track {track} "Synth" "Alchemy" Page {page}/71'.ljust(56))
    update(7, name)
    update(63, raw)
    assert tracker.snapshot()[0] == {}
