"""Deterministic tests for receipt-time frame mode; no native devices."""
import numpy as np
import pytest
from logicprogym.frames import FrameClock, FrameAudio
from logicprogym.env import LogicProEnv
from logicprogym.models import DawEvent, DawSnapshot, EventSource
from tests.test_env import DummyAdapter

def clock():
    now = [0.]
    return now, FrameClock(.05, clock=lambda: now[0],
                          sleeper=lambda n: now.__setitem__(0, now[0]+n))

def test_frame_clock_skips_without_bursts_and_resets():
    now, frames = clock()
    assert frames.wait()['index'] == 1
    now[0] = .23
    frame = frames.wait()
    assert frame['index'] == 5
    assert frame['skipped_frames'] == 3
    assert frame['end_monotonic'] == pytest.approx(.25)
    frames.reset()
    assert frames.wait()['index'] == 1

def test_frame_clock_deadline_crossing_never_sleeps_negative():
    # Cross the deadline between reads, as can happen under scheduler load.
    readings = iter([0., 0., .049, .051, .051, .051])
    sleeps = []

    def sleeper(duration):
        assert 0 < duration <= .02
        sleeps.append(duration)

    frames = FrameClock(.05, clock=lambda: next(readings), sleeper=sleeper)
    assert frames.wait()['index'] == 1
    assert sleeps == pytest.approx([.001])


@pytest.mark.parametrize('duration', [0, -1, float('nan'), True, 2])
def test_invalid_duration(duration):
    with pytest.raises(ValueError):
        FrameClock(duration)

def test_audio_nonoverlap_and_missing_mask():
    audio = FrameAudio(100, 1, .05)
    audio.append(np.ones((10, 1)), .1)
    first, valid, _ = audio.read(0, .05)
    assert first.shape == (5, 1)
    assert valid.sum() == 5
    _, valid, _ = audio.read(.05, .1)
    assert valid.sum() == 5
    _, valid, info = audio.read(.1, .15)
    assert valid.sum() == 0
    assert info['missing_samples'] == 5
    audio.clear()
    assert audio.read(0, .05)[1].sum() == 0

def test_audio_buffer_is_bounded():
    audio = FrameAudio(100, 1, .05)
    audio.append(np.ones((1000, 1)), 10)
    assert audio.samples <= 200
    assert audio.dropped > 0

def test_audio_burst_packets_preserve_samples_across_frames():
    audio = FrameAudio(48000, 1, .05)
    origin = 2325916.0
    samples = np.linspace(-1, 1, 4800, dtype=np.float32).reshape(-1, 1)
    # Model native 62-sample packets arriving together, not at sample cadence.
    for offset in range(0, len(samples), 62):
        packet = samples[offset:offset+62]
        received = origin + 62/48000 if offset == 0 else origin + .1
        audio.append(packet, received)
    for index in range(2):
        frame, valid, info = audio.read(origin+index*.05, origin+(index+1)*.05)
        np.testing.assert_array_equal(frame, samples[index*2400:(index+1)*2400])
        assert valid.sum() == 2400
        assert info['missing_samples'] == info['overlap_samples'] == 0
    # No new data: never repeat old samples or mark padded silence as captured.
    frame, valid, info = audio.read(origin+.1, origin+.15)
    assert not valid.any()
    assert not frame.any()

def test_audio_gap_reanchors_and_reset_forgets_timeline():
    audio = FrameAudio(100, 1, .05)
    audio.append(np.ones((5, 1)), .05)
    audio.append(np.full((5, 1), .5), .2, gap=True)
    assert not audio.read(.1, .15)[1].any()
    frame, valid, info = audio.read(.15, .2)
    assert valid.sum() == 5
    assert info['gap_notifications'] == 1
    assert (frame == .5).all()
    audio.clear()
    assert not audio.read(.15, .2)[1].any()
    audio.append(np.ones((5, 1)), 10.05)
    assert audio.read(10, 10.05)[1].sum() == 5

def test_frame_events_do_not_roll_over_but_notes_persist():
    now, frames = clock()
    adapter = DummyAdapter()
    snapshots = []
    adapter.receive = lambda: snapshots.pop(0) if snapshots else DawSnapshot()
    env = LogicProEnv(adapter, [])
    env.frame_clock = frames
    env.reset()
    note = DawEvent(0, 'agent', EventSource.HUMAN, 'note_on',
                    {'note': 60, 'velocity': .7, '_received_monotonic': .02})
    future = DawEvent(0, 'agent', EventSource.HUMAN, 'note_off',
                      {'note': 60, 'velocity': 0, '_received_monotonic': .05})
    snapshots.append(DawSnapshot(events=(note, future)))
    obs, _, _, _, info = env.step({})
    assert info['frame']['midi_events'] == 1
    assert obs['event_mask'].sum() == 1
    obs, _, _, _, info = env.step({})
    assert info['frame']['midi_events'] == 1
    obs, _, _, _, info = env.step({})
    assert obs['event_mask'].sum() == 0
    env.close()

def test_frame_factory_is_lazy():
    import gymnasium as gym
    env = gym.make('LogicProGym/Logic-v0', config_path='configs/examples/logic_frames.yaml')
    assert env.unwrapped.frame_clock is not None
    assert env.action_space.contains(0)
    assert not env.unwrapped._connected
    env.close()

def test_midi_callback_queue_is_bounded_and_timestamped():
    import mido
    from tests.test_logic_midi_adapter import _adapter
    adapter, backend = _adapter()
    adapter.enable_frames(2)
    for note in (60, 61, 62):
        adapter._capture(adapter.routes[0], mido.Message('note_on', note=note, velocity=64))
    snapshot = adapter.receive()
    assert len(snapshot.events) == 2
    assert snapshot.diagnostics['frame_queue_dropped'] == 1
    assert all('_received_monotonic' in event.values for event in snapshot.events)
    assert not adapter.receive().events
    adapter.close()

def test_audio_wrapper_returns_frame_shape_and_gap_mask():
    from logicprogym.audio import AudioInput, AudioObservation
    capture = AudioInput('test', sample_rate=100, channels=1, window_frames=5)
    capture.frame_buffer = FrameAudio(100, 1, .05)
    capture.frame_buffer.append(np.ones((5, 1)), .05)
    env = AudioObservation(LogicProEnv(DummyAdapter(), []), capture)
    observation, info = env._append({}, {'frame': {'start_monotonic': 0, 'end_monotonic': .05}})
    assert observation['audio'].shape == (5, 1)
    assert observation['audio_valid'].sum() == 5
    assert info['audio']['synchronized_to_logic'] is False
    env.close()

def test_action_is_sent_once_when_frames_are_skipped():
    from tests.test_reset_controls import spec
    now, frames = clock()
    adapter = DummyAdapter()
    env = LogicProEnv(adapter, [spec()])
    env.frame_clock = frames
    env.reset()
    now[0] = .22
    _, _, _, _, info = env.step({'agent/cutoff': [.5]})
    assert len(adapter.commands) == 1
    assert info['frame']['skipped_frames'] == 4
    env.close()
