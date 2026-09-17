"""General backend interface used by DAWs, simulations, and recorded worlds."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from logicprogym.models import DawCommand, DawSnapshot
from logicprogym.world import MusicWorldDescription


@dataclass(frozen=True)
class BackendCapabilities:
    """Features a backend can guarantee before an environment is created."""

    human_events: bool = False
    agent_output: bool = False
    multiple_tracks: bool = False
    transport_read: bool = False
    mixer_parameters: bool = False
    plugin_parameters: bool = False
    audio_features: bool = False
    deterministic_reset: bool = False


class MusicBackend(ABC):
    """Backend-neutral lifecycle for a live, standalone, or replay music world."""

    capabilities = BackendCapabilities()

    @abstractmethod
    def connect(self) -> None:
        """Acquire resources needed by the backend."""
        ...

    @abstractmethod
    def discover_world(self) -> MusicWorldDescription:
        """Describe tracks, controls, devices, participants, and routes."""
        ...

    @abstractmethod
    def observe(self) -> DawSnapshot:
        """Return events and state accumulated since the previous observation."""
        ...

    @abstractmethod
    def apply(self, commands: Sequence[DawCommand]) -> None:
        """Apply agent commands to the shared musical world."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Restore the backend to the beginning of an episode."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources without leaving sound or controls active."""
        ...
