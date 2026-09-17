"""Gymnasium wrappers for composing music tasks without adapter changes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gymnasium as gym


StepReward = Callable[[Any, Any, dict[str, Any]], float]


class FunctionReward(gym.Wrapper):
    """Replace an environment reward using observation, action, and info.

    This keeps research-task objectives outside DAW adapters while retaining
    the ordinary Gymnasium ``step`` contract and wrapper composition model.
    """

    def __init__(self, env: gym.Env, reward: StepReward) -> None:
        super().__init__(env)
        self.reward_function = reward

    def step(self, action):
        observation, _reward, terminated, truncated, info = self.env.step(action)
        reward = float(self.reward_function(observation, action, info))
        return observation, reward, terminated, truncated, info
