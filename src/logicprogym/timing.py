"""Opt-in wall-clock diagnostics, not a real-time scheduler."""
from time import monotonic
import gymnasium as gym

class StepTiming(gym.Wrapper):
    """Measure the inner step, including audio when placed outside that wrapper."""
    def __init__(self, env, *, clock=monotonic):
        super().__init__(env)
        self.clock = clock
        self.previous_start = None

    def reset(self, **kwargs):
        result = self.env.reset(**kwargs)
        self.previous_start = None
        return result

    def step(self, action):
        started = self.clock()
        observation, reward, terminated, truncated, info = self.env.step(action)
        finished = self.clock()
        timing = {
            'step_duration_seconds': finished - started,
            'start_interval_seconds': None if self.previous_start is None else started - self.previous_start,
            'started_monotonic_seconds': started,
            'finished_monotonic_seconds': finished,
        }
        self.previous_start = started
        return observation, reward, terminated, truncated, {**info, 'timing': timing}
