"""Research-facing definitions of controls exposed to an agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionRepresentation(str, Enum):
    """The value exposed to the policy, independent of DAW encoding."""

    CONTINUOUS = "continuous"
    DISCRETE = "discrete"
    BINARY = "binary"
    TRIGGER = "trigger"
    MULTI_DISCRETE = "multi_discrete"


class UpdateMode(str, Enum):
    """How an action value should be interpreted across environment steps."""

    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    TRIGGER = "trigger"
    HOLD = "hold"


@dataclass(frozen=True)
class ActionSpec:
    """Declarative definition of one policy-visible control.

    ``target`` describes musical/DAW meaning, ``representation`` describes what
    the policy emits, and ``encoding`` gives the adapter conversion hints. Keeping
    these independent lets velocity be continuous to a policy but integer MIDI
    on the wire, or deliberately discrete when a researcher wants fixed levels.
    """

    id: str
    track_id: str
    target: str
    representation: ActionRepresentation
    shape: tuple[int, ...] = (1,)
    low: float = 0.0
    high: float = 1.0
    values: tuple[Any, ...] = ()
    dimensions: tuple[tuple[Any, ...], ...] = ()
    update_mode: UpdateMode = UpdateMode.ABSOLUTE
    smoothing_ms: float = 0.0
    encoding: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject inconsistent specifications before an episode can start."""

        if not self.id:
            raise ValueError("Action id cannot be empty")
        if not self.track_id:
            raise ValueError(f"Action {self.id!r} must target a track")
        if any(size <= 0 for size in self.shape):
            raise ValueError(f"Action {self.id!r} has an invalid shape")
        if self.low > self.high:
            raise ValueError(f"Action {self.id!r} has low greater than high")
        if self.representation is ActionRepresentation.DISCRETE and not self.values:
            raise ValueError(f"Discrete action {self.id!r} has no values")
        if (
            self.representation is ActionRepresentation.MULTI_DISCRETE
            and (not self.dimensions or any(not dimension for dimension in self.dimensions))
        ):
            raise ValueError(f"Multi-discrete action {self.id!r} has no dimensions")


# Backward-compatible alias for the action representation enum.
ActionType = ActionRepresentation
