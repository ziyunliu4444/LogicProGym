"""Public construction helpers for configured LogicProGym environments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv, RewardFunction


def adapter_from_config(config: LogicProGymConfig):
    """Construct the configured adapter without connecting to the DAW yet."""

    adapter_type = config.adapter.get("type")
    if adapter_type == "logic_midi":
        from logicprogym.adapters.logic import LogicMidiAdapter

        return LogicMidiAdapter.from_config(config.adapter)
    if adapter_type == "logic_mackie":
        from logicprogym.adapters.logic_mackie import LogicMackieAdapter

        return LogicMackieAdapter.from_config(config.adapter)
    if adapter_type == "logic_hybrid":
        from logicprogym.adapters.logic_hybrid import LogicHybridAdapter

        return LogicHybridAdapter.from_config(config.adapter)
    if adapter_type == "logic":
        raise ValueError(
            "adapter.type 'logic' is only a placeholder; choose 'logic_midi', "
            "'logic_mackie', or 'logic_hybrid'"
        )
    raise ValueError(f"Unknown adapter.type {adapter_type!r}")


def make(
    config_path: str | Path,
    *,
    reward: RewardFunction | None = None,
    render_mode: str | None = None,
) -> LogicProEnv:
    """Create a lazy Logic/Gymnasium environment from one YAML file.

    MIDI ports are opened only when ``reset()`` is called, so researchers can
    construct and wrap the environment before Logic is running.
    """

    if render_mode is not None:
        raise ValueError("LogicProGym 1.0 does not define a render mode")
    config = LogicProGymConfig.from_yaml(config_path)
    from logicprogym.control_setup import validate_routes
    validate_routes(config)
    timing = config.environment.get("timing", False)
    if not isinstance(timing, bool):
        raise ValueError("environment.timing must be boolean")
    env = LogicProEnv.from_config(adapter_from_config(config), config, reward=reward)
    frames = config.environment.get('frames')
    frame_clock = None
    if frames is not None:
        from logicprogym.frames import FrameClock
        if not isinstance(frames, dict) or set(frames) - {'enabled', 'duration_seconds'}:
            raise ValueError('frames accepts enabled and duration_seconds only')
        if not isinstance(frames.get('enabled', False), bool):
            raise ValueError('frames.enabled must be boolean')
        if frames.get('enabled', False):
            frame_clock = FrameClock(frames.get('duration_seconds', .05))
            env.frame_clock = frame_clock
            if not env.action_specs:
                # Gymnasium rejects empty Dict spaces. Observation-only frames
                # expose one explicit no-op action instead.
                import gymnasium as gym
                env.action_space = gym.spaces.Discrete(1)
            midi = getattr(env.adapter, 'midi', env.adapter)
            if hasattr(midi, 'enable_frames'):
                midi.enable_frames(env.event_capacity * 16)
    audio = config.environment.get('audio')
    if audio and audio.get('enabled', True):
        from logicprogym.audio import AudioInput, AudioObservation
        options = {k: v for k, v in audio.items() if k not in {'enabled', 'source'}}
        source = audio.get('source', 'device')
        if frame_clock is not None:
            from logicprogym.frames import FrameAudio
            rate = options.get('sample_rate')
            if not isinstance(rate, int) or isinstance(rate, bool) or rate <= 0:
                raise ValueError('Frame audio requires an explicit positive sample_rate')
            frame_audio = FrameAudio(rate, options.get('channels', 2), frame_clock.duration)
            options['window_frames'] = frame_audio.frames
        if source == 'native':
            from logicprogym.native_audio import NativeAudioInput
            capture = NativeAudioInput(**options)
        elif source == 'device':
            capture = AudioInput(**options)
        else:
            raise ValueError("audio.source must be 'native' or 'device'")
        if frame_clock is not None:
            capture.frame_buffer = frame_audio
        env = AudioObservation(env, capture)
    if timing:
        from logicprogym.timing import StepTiming
        env = StepTiming(env)
    return env


def make_registered_env(**kwargs: Any) -> LogicProEnv:
    """Gymnasium registry entry point used by ``gym.make``."""

    return make(**kwargs)
