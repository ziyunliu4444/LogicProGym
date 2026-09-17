"""Backend-neutral description of a musical world shared by humans and agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from logicprogym.models import ParameterDescriptor, TrackDescriptor


class ParticipantRole(str, Enum):
    """Kinds of participants that can observe or modify the world."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class ControlKind(str, Enum):
    """Policy semantics of a world control, independent of backend encoding."""

    CONTINUOUS = "continuous"
    DISCRETE = "discrete"
    BINARY = "binary"
    TRIGGER = "trigger"
    VECTOR = "vector"


class AccessPolicy(str, Enum):
    """Which participant may modify a control."""

    HUMAN_ONLY = "human_only"
    AGENT_ONLY = "agent_only"
    SHARED = "shared"


class ConflictPolicy(str, Enum):
    """How simultaneous human and agent contributions are combined."""

    LATEST = "latest"
    HUMAN_PRIORITY = "human_priority"
    ADDITIVE = "additive"
    BLEND = "blend"


@dataclass(frozen=True)
class ParticipantDescriptor:
    """A human, learning agent, or world service taking part in a session."""

    id: str
    name: str
    role: ParticipantRole


@dataclass(frozen=True)
class DeviceDescriptor:
    """An instrument, effect, controller, or backend device on a track."""

    id: str
    track_id: str
    name: str
    kind: str
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ControlDescriptor:
    """A named musical control exposed consistently across world backends."""

    id: str
    track_id: str
    name: str
    kind: ControlKind = ControlKind.CONTINUOUS
    device_id: str | None = None
    minimum: float = 0.0
    maximum: float = 1.0
    default: float = 0.0
    values: tuple[Any, ...] = ()
    writable: bool = True
    access: AccessPolicy = AccessPolicy.SHARED
    conflict: ConflictPolicy = ConflictPolicy.LATEST
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError(f"Control {self.id!r} has minimum greater than maximum")
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError(f"Control {self.id!r} default is outside its range")
        if self.kind is ControlKind.DISCRETE and not self.values:
            raise ValueError(f"Discrete control {self.id!r} has no values")

    def parameter_descriptor(self) -> ParameterDescriptor:
        """Create the numerical parameter view consumed by current Gym spaces."""

        return ParameterDescriptor(
            id=self.id,
            track_id=self.track_id,
            name=self.name,
            minimum=self.minimum,
            maximum=self.maximum,
            writable=self.writable,
        )


@dataclass(frozen=True)
class RouteDescriptor:
    """A directed event or audio route between world tracks/devices."""

    source_id: str
    destination_id: str
    kind: str = "event"


@dataclass(frozen=True)
class MusicWorldDescription:
    """Discoverable structure and capabilities of one connected music world."""

    id: str
    name: str
    tracks: tuple[TrackDescriptor, ...]
    controls: tuple[ControlDescriptor, ...] = ()
    devices: tuple[DeviceDescriptor, ...] = ()
    participants: tuple[ParticipantDescriptor, ...] = ()
    routes: tuple[RouteDescriptor, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def parameters(self) -> tuple[ParameterDescriptor, ...]:
        """Compatibility view for the existing numerical parameter registry."""

        return tuple(control.parameter_descriptor() for control in self.controls)
