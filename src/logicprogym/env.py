"""Generic Gymnasium environment independent of any particular DAW."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import gymnasium as gym
import numpy as np
import threading

from logicprogym.actions.processor import ActionProcessor
from logicprogym.actions.specs import ActionSpec
from logicprogym.backends.base import MusicBackend
from logicprogym.models import DawSnapshot
from logicprogym.observations import ObservationBuilder
from logicprogym.observation_selection import ObservationSelection
from logicprogym.registry import SessionRegistry
from logicprogym.spaces import build_action_space, build_observation_space
from logicprogym.validation import validate_capabilities


# Rewards belong to research tasks, not DAW adapters. This callback keeps that
# separation while allowing the initial environment to remain lightweight.
RewardFunction = Callable[[DawSnapshot, dict[str, object]], float]


class LogicProEnv(gym.Env):
    """Coordinate a Gymnasium policy with a DAW-neutral adapter.

    The environment owns Gymnasium lifecycle and space definitions. The adapter
    owns all DAW-specific communication. This dependency boundary allows the
    same task and policy to run against Logic, Ableton, REAPER, or another DAW.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        adapter: MusicBackend,
        actions: Sequence[ActionSpec],
        *,
        event_capacity: int = 128,
        max_tracks: int = 16,
        max_parameters: int = 256,
        observed_fields: Sequence[str] = (),
        track_observations: Mapping[str, Sequence[str]] | None = None,
        reward: RewardFunction | None = None,
        reset_controls: dict | None = None,
    ) -> None:
        """Create stable spaces from action specs without connecting to a DAW."""

        super().__init__()
        # ``adapter`` remains the public argument name for backward compatibility;
        # internally it may now be a DAW, standalone, replay, or future backend.
        self.backend = adapter
        self.adapter = adapter
        self.action_specs = tuple(actions)
        from logicprogym.reset_controls import reset_commands
        self._reset_commands = reset_commands(self.action_specs, reset_controls)
        self.action_processor = ActionProcessor(self.action_specs)
        self.event_capacity = event_capacity
        self.reward_function = reward
        self.observation_selection = (None if track_observations is None
                                      else ObservationSelection(track_observations))
        self.observed_fields = (tuple(observed_fields) if track_observations is None else
                               tuple(field for fields in track_observations.values() for field in fields))
        # Reject impossible experiments before opening ports or starting a DAW.
        validate_capabilities(
            adapter.capabilities, self.action_specs, self.observed_fields
        )
        self.registry = SessionRegistry(max_tracks, max_parameters)
        self.observation_builder = ObservationBuilder(
            self.registry, event_capacity,
            note_activity_from_kind=self.observation_selection is not None)
        self.action_space = build_action_space(self.action_specs)
        self.observation_space = build_observation_space(
            event_capacity, max_tracks, max_parameters
        )
        self.frame_clock = None
        self._connected = False
        self._cleanup_thread = None
        self._cleanup_errors = []

    @classmethod
    def from_config(cls, adapter: MusicBackend, config, *, reward=None) -> "LogicProEnv":
        """Construct an environment from a loaded :class:`LogicProGymConfig`.

        The loose annotation avoids coupling the core environment module back to
        the YAML loader while still providing a convenient researcher workflow.
        """

        environment = config.environment
        observed_fields = tuple(
            field for track in config.tracks for field in track.observe
        )
        return cls(
            adapter,
            config.actions,
            event_capacity=int(environment.get("event_capacity", 128)),
            max_tracks=int(environment.get("max_tracks", 16)),
            max_parameters=int(environment.get("max_parameters", 256)),
            observed_fields=observed_fields,
            track_observations={track.alias: track.observe for track in config.tracks},
            reward=reward,
            reset_controls=environment.get("reset_controls"),
        )

    def _observation(self, snapshot: DawSnapshot) -> dict[str, np.ndarray]:
        """Convert a canonical snapshot into fixed-shape numerical arrays."""

        observation = self.observation_builder.build(snapshot)
        if self.observation_selection is not None:
            observation = self.observation_selection.mask(observation, self.registry)
        return observation

    def _select_snapshot(self, snapshot: DawSnapshot) -> DawSnapshot:
        """Use the same selected state for observations, rewards, and public info."""
        if self.observation_selection is None:
            return snapshot
        return self.observation_selection.snapshot(snapshot, self.registry)

    def reset(self, *, seed=None, options=None):
        """Connect lazily and return the latest DAW snapshot."""

        if self._cleanup_thread is not None:
            if self._cleanup_thread.is_alive():
                raise RuntimeError("Previous DAW cleanup is still running; cannot reconnect")
            if self._cleanup_errors:
                raise RuntimeError("Previous DAW cleanup failed") from self._cleanup_errors[0]
        super().reset(seed=seed)
        if not self._connected:
            self.backend.connect()
            world = self.backend.discover_world()
            self.registry.bind(world.tracks, world.parameters)
            self._connected = True
        else:
            # Resetting an existing session must not leave notes hanging in the DAW.
            releases = self.action_processor.reset()
            if releases:
                self.backend.apply(releases)
        self.backend.reset()
        if self._reset_commands:
            self.backend.apply(self._reset_commands)
        self.observation_builder.reset()
        snapshot = self._select_snapshot(self.backend.observe())
        if self.frame_clock is not None:
            self.frame_clock.reset()
            self.frame_clock.drop_baseline = snapshot.diagnostics.get("midi", snapshot.diagnostics).get("frame_queue_dropped", 0)
        return self._observation(snapshot), {"snapshot": snapshot,
            "reset_controls": {"status": "sent" if self._reset_commands else "disabled",
                "confirmed": False, "commands": [
                    {"track": c.track_id, "target": c.kind, "value": c.values["value"]}
                    for c in self._reset_commands]}}

    def step(self, action):
        """Compile one policy action, send it, then observe the resulting state."""

        if not self._connected:
            raise RuntimeError("Call reset before step; the environment is disconnected")
        if self.frame_clock is not None and not self.action_specs and isinstance(self.action_space, gym.spaces.Discrete):
            if not self.action_space.contains(action):
                raise ValueError('Observation-only frames require no-op action 0')
            action = {}
        commands = self.action_processor.process(action)
        self.backend.apply(commands)
        frame = None if self.frame_clock is None else self.frame_clock.wait()
        snapshot = self._select_snapshot(self.backend.observe())
        if frame is not None:
            snapshot = self.frame_clock.snapshot(snapshot, self.observation_builder, frame)
        reward = 0.0 if self.reward_function is None else self.reward_function(snapshot, action)
        return self._observation(snapshot), float(reward), False, False, {"snapshot": snapshot, **({"frame": frame} if frame is not None else {})}

    def close(self, timeout: float = 3.0) -> None:
        """Release notes and ports, reporting stalled cleanup without exiting Python.

        A timed-out native close cannot safely be killed by Python. Keep its
        worker alive and reject reconnection until it completes; never pretend
        that its MIDI endpoints were successfully released.
        """
        if timeout <= 0:
            raise ValueError("close timeout must be positive")
        if self._connected:
            self._connected = False
            commands = self.action_processor.emergency_stop()
            self._cleanup_errors = []

            def cleanup():
                try:
                    self.backend.apply(commands)
                except BaseException as error:
                    self._cleanup_errors.append(error)
                finally:
                    try:
                        self.backend.close()
                    except BaseException as error:
                        self._cleanup_errors.append(error)

            self._cleanup_thread = threading.Thread(
                target=cleanup, name="logicprogym-close", daemon=True
            )
            self._cleanup_thread.start()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout)
            if self._cleanup_thread.is_alive():
                raise TimeoutError("DAW cleanup is still running; MIDI ports may remain open")
            if self._cleanup_errors:
                raise RuntimeError("DAW cleanup failed") from self._cleanup_errors[0]


# Backend-neutral alias; LogicProEnv remains a supported public name.
MusicWorldEnv = LogicProEnv
