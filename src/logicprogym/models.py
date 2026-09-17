"""Canonical data exchanged between a DAW adapter and Gymnasium."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventSource(str, Enum):
    """Origin of an event observed in the DAW.

    Provenance prevents an agent command echoed by the DAW from being mistaken
    for a human performance event.
    """

    HUMAN = "human"
    AGENT = "agent"
    DAW = "daw"


@dataclass(frozen=True)
class TrackDescriptor:
    """Stable, DAW-neutral description of one discovered track."""

    id: str
    name: str
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ParameterDescriptor:
    """A controllable or observable DAW/plugin parameter."""

    id: str
    track_id: str
    name: str
    minimum: float = 0.0
    maximum: float = 1.0
    writable: bool = True


@dataclass(frozen=True)
class TransportState:
    """Musical transport data at the instant a snapshot was captured.

    Sample position is the authoritative real-time clock. Beat position and
    tempo are included so tasks can also reason in musical time.
    """

    sample_position: int = 0
    sample_rate: float = 44_100.0
    tempo: float = 120.0
    beat_position: float = 0.0
    playing: bool = False


@dataclass(frozen=True)
class DawEvent:
    """An event produced by a human, the agent, or the DAW itself."""

    timestamp_samples: int
    track_id: str
    source: EventSource
    kind: str
    values: dict[str, Any] = field(default_factory=dict)
    command_id: str | None = None


@dataclass(frozen=True)
class DawCommand:
    """DAW-neutral instruction emitted after compiling a policy action.

    Adapters translate this semantic command into MIDI, a control-surface
    message, or a native plug-in/DAW protocol.
    """

    track_id: str
    kind: str
    values: dict[str, Any]
    timestamp_samples: int | None = None
    command_id: str | None = None


@dataclass(frozen=True)
class DawSnapshot:
    """Immutable view of DAW state returned for one environment step."""

    transport: TransportState = TransportState()
    events: tuple[DawEvent, ...] = ()
    parameter_values: dict[str, float] = field(default_factory=dict)
    # Adapter-specific measurements such as estimated bridge time and queue delay.
    diagnostics: dict[str, Any] = field(default_factory=dict)


# Neutral public names for new code. The original DAW names remain aliases so
# recordings, adapters, and existing researchers do not face a breaking change.
MusicEvent = DawEvent
MusicCommand = DawCommand
MusicWorldSnapshot = DawSnapshot
