"""Gymnasium environments for music worlds shared by humans and agents."""

from gymnasium.envs.registration import register, registry as gym_registry

from logicprogym.backends import BackendCapabilities, MusicBackend, StandaloneBackend
from logicprogym.env import LogicProEnv, MusicWorldEnv
from logicprogym.factory import make
from logicprogym.models import MusicCommand, MusicEvent, MusicWorldSnapshot
from logicprogym.wrappers import FunctionReward
from logicprogym.audio import AudioInput, AudioObservation
from logicprogym.world import MusicWorldDescription

ENV_ID = "LogicProGym/Logic-v0"
if ENV_ID not in gym_registry:
    register(id=ENV_ID, entry_point="logicprogym.factory:make_registered_env")

__all__ = [
    "AudioInput",
    "AudioObservation",
    "BackendCapabilities",
    "LogicProEnv",
    "ENV_ID",
    "FunctionReward",
    "MusicBackend",
    "MusicCommand",
    "MusicEvent",
    "MusicWorldDescription",
    "MusicWorldEnv",
    "MusicWorldSnapshot",
    "StandaloneBackend",
    "make",
]
