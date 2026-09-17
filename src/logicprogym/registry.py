"""Stable numerical slots for dynamic DAW tracks and parameters."""

from __future__ import annotations

from collections.abc import Sequence

from logicprogym.models import ParameterDescriptor, TrackDescriptor


class SessionRegistry:
    """Map DAW identifiers to fixed Gymnasium indices for one connection.

    A DAW may discover tracks dynamically, while an environment's spaces must
    remain fixed during an episode. Capacity-limited slots reconcile those two
    constraints and make masks meaningful to a policy.
    """

    def __init__(self, max_tracks: int, max_parameters: int) -> None:
        if max_tracks <= 0 or max_parameters <= 0:
            raise ValueError("Registry capacities must be positive")
        self.max_tracks = max_tracks
        self.max_parameters = max_parameters
        self.tracks: tuple[TrackDescriptor, ...] = ()
        self.parameters: tuple[ParameterDescriptor, ...] = ()
        self._track_slots: dict[str, int] = {}
        self._parameter_slots: dict[str, int] = {}

    def bind(
        self,
        tracks: Sequence[TrackDescriptor],
        parameters: Sequence[ParameterDescriptor],
    ) -> None:
        """Freeze discovered identifiers into deterministic connection slots."""

        if len(tracks) > self.max_tracks:
            raise ValueError(
                f"DAW exposed {len(tracks)} tracks but capacity is {self.max_tracks}"
            )
        if len(parameters) > self.max_parameters:
            raise ValueError(
                f"DAW exposed {len(parameters)} parameters but capacity is "
                f"{self.max_parameters}"
            )
        track_ids = [track.id for track in tracks]
        parameter_ids = [parameter.id for parameter in parameters]
        if len(track_ids) != len(set(track_ids)):
            raise ValueError("DAW track identifiers must be unique")
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError("DAW parameter identifiers must be unique")

        self.tracks = tuple(tracks)
        self.parameters = tuple(parameters)
        self._track_slots = {track.id: slot for slot, track in enumerate(self.tracks)}
        self._parameter_slots = {
            parameter.id: slot for slot, parameter in enumerate(self.parameters)
        }

    def track_slot(self, track_id: str) -> int:
        """Resolve a DAW track identifier or fail instead of misrouting data."""

        try:
            return self._track_slots[track_id]
        except KeyError as error:
            raise KeyError(f"Unknown DAW track id: {track_id!r}") from error

    def parameter_slot(self, parameter_id: str) -> int:
        """Resolve a discovered parameter identifier to its observation slot."""

        try:
            return self._parameter_slots[parameter_id]
        except KeyError as error:
            raise KeyError(f"Unknown DAW parameter id: {parameter_id!r}") from error
