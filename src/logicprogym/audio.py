"""Optional live audio windows for Gymnasium policies."""

from threading import Lock
from time import monotonic

import gymnasium as gym
import numpy as np


class AudioInput:
    """Capture a bounded rolling window from an explicitly selected input device."""

    def __init__(self, device, sample_rate=48000, channels=2, window_frames=4800,
                 stream_factory=None):
        if device is None:
            raise ValueError('Choose an explicit audio input device')
        for name, value in [('sample_rate', sample_rate), ('channels', channels),
                            ('window_frames', window_frames)]:
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f'{name} must be a positive integer')
        self.device, self.sample_rate = device, sample_rate
        self.channels, self.window_frames = channels, window_frames
        self.stream_factory = stream_factory
        self.stream = None
        self.lock = Lock()
        self.buffer = np.zeros((window_frames, channels), dtype=np.float32)
        self.clear()

    def clear(self):
        if hasattr(self, "frame_buffer"):
            self.frame_buffer.clear()
        with self.lock:
            self.buffer.fill(0)
            self.count = 0
            self.sequence = 0
            self.updated = None
            self.overflows = 0

    def _capture(self, data, frames, timing, status):
        if hasattr(self, "frame_buffer"):
            self.frame_buffer.append(data, monotonic(), bool(status))
        # Do no file I/O, printing, or feature extraction on the audio callback.
        with self.lock:
            if status:
                self.overflows += 1
                self.count = 0
                self.buffer.fill(0)
            data = np.nan_to_num(data[-self.window_frames:], nan=0, posinf=1, neginf=-1)
            n = len(data)
            if n == 0:
                return
            self.buffer[:-n] = self.buffer[n:]
            self.buffer[-n:] = np.clip(data, -1, 1)
            self.count = min(self.window_frames, self.count + n)
            self.sequence += 1
            self.updated = monotonic()

    def start(self):
        if self.stream is not None:
            return
        factory = self.stream_factory
        if factory is None:
            try:
                import sounddevice
            except ImportError as error:
                raise ImportError("Audio dependency missing; reinstall LogicProGym: python -m pip install -e .") from error
            factory = sounddevice.InputStream
        self.stream = factory(device=self.device, samplerate=self.sample_rate,
                              channels=self.channels, dtype='float32', callback=self._capture)
        try:
            self.stream.start()
        except BaseException:
            self.close()
            raise

    def read(self):
        with self.lock:
            age = None if self.updated is None else monotonic() - self.updated
            valid = np.zeros(self.window_frames, dtype=np.int8)
            if self.count and age <= max(.5, 2 * self.window_frames / self.sample_rate):
                valid[-self.count:] = 1
            return self.buffer.copy(), valid, dict(
                sample_rate=self.sample_rate, device=self.device, age_seconds=age,
                sequence=self.sequence, callback_status_count=self.overflows)

    def close(self):
        if self.stream is not None:
            stream, self.stream = self.stream, None
            try:
                stream.abort()
            finally:
                stream.close()


class AudioObservation(gym.Wrapper):
    """Append raw PCM audio and a frame mask; reward remains task-defined."""

    def __init__(self, env, audio_input):
        super().__init__(env)
        if not isinstance(env.observation_space, gym.spaces.Dict):
            raise ValueError('AudioObservation requires a Dict observation space')
        self.audio_input = audio_input
        spaces = dict(env.observation_space.spaces)
        if {'audio', 'audio_valid'} & spaces.keys():
            raise ValueError('Audio observation keys already exist')
        spaces['audio'] = gym.spaces.Box(-1, 1, (audio_input.window_frames, audio_input.channels), np.float32)
        spaces['audio_valid'] = gym.spaces.MultiBinary(audio_input.window_frames)
        self.observation_space = gym.spaces.Dict(spaces)

    def _append(self, observation, info):
        if hasattr(self.audio_input, 'frame_buffer'):
            if self.audio_input.sample_rate != self.audio_input.frame_buffer.rate:
                raise RuntimeError('Audio rate changed during frame capture')
            frame = info.get('frame')
            start, end = (frame['start_monotonic'], frame['end_monotonic']) if frame else (0, 0)
            # Read normally too, so native helper failures still propagate.
            _, _, details = self.audio_input.read()
            audio, valid, frame_details = self.audio_input.frame_buffer.read(start, end)
            details.update(frame_details)
        else:
            audio, valid, details = self.audio_input.read()
        return {**observation, 'audio': audio, 'audio_valid': valid}, {**info, 'audio': details}

    def reset(self, **kwargs):
        try:
            self.audio_input.start()
            observation, info = self.env.reset(**kwargs)
            self.audio_input.clear()
            return self._append(observation, info)
        except BaseException:
            self.close()
            raise

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)
        observation, info = self._append(observation, info)
        return observation, reward, terminated, truncated, info

    def close(self):
        # Release agent notes even if audio cleanup fails.
        try:
            self.env.close()
        finally:
            self.audio_input.close()
