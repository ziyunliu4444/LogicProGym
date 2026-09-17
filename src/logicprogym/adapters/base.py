"""Contract implemented by every DAW integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from logicprogym.backends.base import BackendCapabilities, MusicBackend
from logicprogym.models import DawCommand, DawSnapshot, ParameterDescriptor, TrackDescriptor
from logicprogym.world import (
    ControlDescriptor,
    MusicWorldDescription,
    ParticipantDescriptor,
    ParticipantRole,
)


# Backward-compatible name retained for existing adapters and user code.
AdapterCapabilities = BackendCapabilities


class LogicProAdapter(MusicBackend, ABC):
    """Interface separating DAW communication from Gymnasium behavior."""

    # Conservative defaults ensure an unfinished adapter never claims support.
    capabilities = AdapterCapabilities()

    @abstractmethod
    def connect(self) -> None:
        """Open the bridge connection and acquire required resources."""
        ...

    @abstractmethod
    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        """Return tracks and parameters currently exposed by the DAW session."""
        ...

    @abstractmethod
    def receive(self) -> DawSnapshot:
        """Return the most recent synchronized DAW state."""
        ...

    @abstractmethod
    def send(self, commands: Sequence[DawCommand]) -> None:
        """Deliver canonical commands using the adapter's concrete protocol."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release ports, sockets, plug-in connections, and active notes safely."""
        ...

    def discover_world(self) -> MusicWorldDescription:
        """Translate the legacy DAW discovery pair into a music-world schema."""

        tracks, parameters = self.discover()
        controls = tuple(
            ControlDescriptor(
                id=parameter.id,
                track_id=parameter.track_id,
                name=parameter.name,
                minimum=parameter.minimum,
                maximum=parameter.maximum,
                writable=parameter.writable,
            )
            for parameter in parameters
        )
        return MusicWorldDescription(
            id=self.__class__.__name__,
            name=self.__class__.__name__,
            tracks=tuple(tracks),
            controls=controls,
            participants=(
                ParticipantDescriptor("human", "Human", ParticipantRole.HUMAN),
                ParticipantDescriptor("agent", "Agent", ParticipantRole.AGENT),
            ),
            metadata={"backend_kind": "daw_adapter"},
        )

    def observe(self) -> DawSnapshot:
        """Compatibility wrapper around the original adapter receive method."""

        return self.receive()

    def apply(self, commands: Sequence[DawCommand]) -> None:
        """Compatibility wrapper around the original adapter send method."""

        self.send(commands)

    def reset(self) -> None:
        """Legacy DAW adapters currently reset through environment note cleanup."""

        return None
