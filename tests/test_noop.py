"""Action-free sessions obey Gymnasium without issuing backend actions."""
import gymnasium as gym
import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from logicprogym.env import LogicProEnv
from logicprogym.factory import make
from tests.test_env import DummyAdapter


def test_noop_checker_and_no_backend_apply():
    adapter = DummyAdapter()
    env = LogicProEnv(adapter, [])
    assert env.action_space == gym.spaces.Discrete(1)
    check_env(env, skip_render_check=True)
    env.reset()
    calls = []
    adapter.apply = lambda commands: calls.append(commands)
    try:
        for action in (0, np.int64(0), env.action_space.sample()):
            obs, reward, terminated, truncated, info = env.step(action)
            assert env.observation_space.contains(obs)
            assert reward == 0 and not terminated and not truncated
        assert calls == []
    finally:
        env.close()


@pytest.mark.parametrize('action', [1, -1, 0.0, {}, [], np.array([0])])
def test_invalid_noop_never_reaches_backend(action):
    env = LogicProEnv(DummyAdapter(), [])
    env.reset()
    try:
        with pytest.raises(ValueError, match='no-op action 0'):
            env.step(action)
    finally:
        env.close()


def test_noop_reward_and_time_limit():
    received = []
    def reward(snapshot, action):
        received.append(action)
        return 2.0
    env = gym.wrappers.TimeLimit(LogicProEnv(DummyAdapter(), [], reward=reward), 2)
    try:
        env.reset()
        assert env.step(0)[3] is False
        assert env.step(0)[1:4] == (2.0, False, True)
        assert received == [{}, {}]
    finally:
        env.close()


@pytest.mark.parametrize('template', ['logic_discovery.yaml', 'logic_frames.yaml'])
def test_noop_factory_and_registered_construction(template):
    path = 'configs/examples/' + template
    for env in (make(path), gym.make('LogicProGym/Logic-v0', config_path=path)):
        try:
            assert env.action_space == gym.spaces.Discrete(1)
            assert not env.unwrapped._connected
        finally:
            env.close()
