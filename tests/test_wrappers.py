"""Tests for task composition through standard Gymnasium wrappers."""

import gymnasium as gym

from logicprogym.wrappers import FunctionReward


class OneStepEnv(gym.Env):
    action_space = gym.spaces.Discrete(2)
    observation_space = gym.spaces.Discrete(3)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return 0, {"target": 2}

    def step(self, action):
        return action, -999.0, False, False, {"target": 2}


def test_function_reward_uses_transition_context() -> None:
    env = FunctionReward(
        OneStepEnv(),
        lambda observation, action, info: -abs(info["target"] - observation),
    )
    observation, reward, terminated, truncated, info = env.step(1)
    assert observation == 1
    assert reward == -1.0
    assert not terminated and not truncated
    assert info["target"] == 2
