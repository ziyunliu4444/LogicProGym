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
