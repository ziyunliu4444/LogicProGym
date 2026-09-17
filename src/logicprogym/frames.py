"""Local receipt-time frames, not synchronized Logic transport ticks."""
from collections import deque
from dataclasses import replace
import math
from threading import Lock
from time import monotonic, sleep
import numpy as np

class FrameClock:
    """Skip missed intervals; never repeat an action to catch up."""
    def __init__(self, duration, *, clock=monotonic, sleeper=sleep):
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not .01 <= duration <= 1:
            raise ValueError('frames.duration_seconds must be between 0.01 and 1')
        self.duration, self.clock, self.sleep = duration, clock, sleeper
        self.reset()

    def reset(self):
        self.origin = self.clock()
        self.index = 0
        self.pending = []
        self.midi_state_valid = True
        self.drop_baseline = 0

    def wait(self):
        now = self.clock()
        index = max(self.index + 1, math.floor((now - self.origin) / self.duration) + 1)
        end = self.origin + index * self.duration
        while True:
            # Use one clock reading for both the check and sleep duration:
            # the deadline can pass between two separate clock readings.
            remaining = end - self.clock()
            if remaining <= 0:
                break
            self.sleep(min(.02, remaining))
        # If the scheduler overslept, expose the latest completed interval.
        index = max(index, math.floor((self.clock() - self.origin) / self.duration + 1e-9))
        end = self.origin + index * self.duration
        info = dict(index=index, start_monotonic=end-self.duration, end_monotonic=end,
                    duration_seconds=self.duration, skipped_frames=index-self.index-1,
                    lateness_seconds=max(0., self.clock()-end),
                    clock_source='local_receipt_time', synchronized_to_logic=False)
        self.index = index
        return info

    def snapshot(self, snapshot, builder, info):
        events = self.pending + list(snapshot.events)
        earlier, current, future = [], [], []
        missing = 0
        for event in events:
            received = event.values.get('_received_monotonic')
            if received is None:
                missing += 1
                continue
            if received < info['start_monotonic']:
                earlier.append(event)
            elif received < info['end_monotonic']:
                current.append(event)
            else:
                future.append(event)
        # Future receipts are retained for the next frame; bound even a faulty source.
        capacity = builder.event_capacity * 16
        self.pending = future[-capacity:]
        diagnostics = snapshot.diagnostics.get('midi', snapshot.diagnostics)
        drops = max(0, diagnostics.get('frame_queue_dropped', 0) - self.drop_baseline)
        if drops or missing or len(future) > capacity:
            self.midi_state_valid = False
        for event in earlier + current:
            builder._apply_note_state(event, builder.registry.track_slot(event.track_id))
        # Frame events are not the normal rolling history. Held-note state persists.
        builder._event_history.clear()
        info.update(midi_events=len(current), events_truncated=max(0, len(current)-builder.event_capacity),
                    skipped_interval_events=len(earlier), missing_receipt_timestamps=missing,
                    midi_queue_dropped=drops, midi_state_valid=self.midi_state_valid)
        return replace(snapshot, events=tuple(current))

class FrameAudio:
    """Continuous sample timeline anchored to first receipt, not hardware time."""
    def __init__(self, sample_rate, channels, duration):
        if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (sample_rate, channels)):
            raise ValueError("Audio rate and channels must be positive integers")
        frames = sample_rate * duration
        if not math.isclose(frames, round(frames), abs_tol=1e-7):
            raise ValueError('Audio sample_rate * frame duration must be an integer')
        self.rate, self.channels, self.frames = sample_rate, channels, round(frames)
        self.lock = Lock()
        self.clear()

    def clear(self):
        with self.lock:
            self.chunks = deque()
            self.samples = 0
            self.dropped = 0
            self.gaps = 0
            self.origin = None
            self.next_sample = 0

    def append(self, data, received, gap=False):
        if len(data) == 0:
            return
        with self.lock:
            if gap:
                self.chunks.clear()
                self.samples = 0
                self.gaps += 1
                self.origin = None
                self.next_sample = 0
            # Packet arrival jitter must not change the spacing of PCM samples.
            # Re-anchor only at startup/reset or an explicitly reported gap.
            if self.origin is None:
                self.origin = received - len(data) / self.rate
            first_sample = self.next_sample
            self.next_sample += len(data)
            data = np.clip(np.nan_to_num(data, nan=0, posinf=1, neginf=-1), -1, 1).copy()
            # Keep at most two seconds and cap one oversized callback as well.
            capacity = self.rate * 2
            if len(data) > capacity:
                self.dropped += len(data)-capacity
                first_sample += len(data)-capacity
                data = data[-capacity:]
            self.chunks.append((first_sample, data))
            self.samples += len(data)
            while self.samples > capacity:
                _, old = self.chunks.popleft()
                self.samples -= len(old)
                self.dropped += len(old)

    def read(self, start, end):
        audio = np.zeros((self.frames, self.channels), np.float32)
        valid = np.zeros(self.frames, np.int8)
        overlaps = 0
        with self.lock:
            if end > start and self.origin is not None:
                # Integer offsets preserve every sample exactly once. Tolerance
                # handles cancellation in large monotonic clock values.
                first = math.ceil((start-self.origin)*self.rate - 1e-4)
                last = first + self.frames
                while self.chunks and self.chunks[0][0] + len(self.chunks[0][1]) <= first:
                    _, old = self.chunks.popleft()
                    self.samples -= len(old)
                for offset, data in self.chunks:
                    lo, hi = max(first, offset), min(last, offset+len(data))
                    if hi <= lo:
                        continue
                    slots = slice(lo-first, hi-first)
                    overlaps += int(valid[slots].sum())
                    audio[slots] = data[lo-offset:hi-offset]
                    valid[slots] = 1
            return audio, valid, dict(sample_rate=self.rate, frame_audio=True,
                missing_samples=int((valid == 0).sum()), overlap_samples=overlaps,
                dropped_buffer_samples=self.dropped, gap_notifications=self.gaps, clock_source='sample_count_receipt_anchored',
                synchronized_to_logic=False)
