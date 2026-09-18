"""Stateful conversion of canonical DAW snapshots into numerical observations."""

from __future__ import annotations

from collections import deque

import numpy as np

from logicprogym.models import DawEvent, DawSnapshot, EventSource
from logicprogym.registry import SessionRegistry


# Public numeric codes remain stable across adapters and recorded datasets.
EVENT_KIND_CODES = {
    "note_on": 0,
    "note_off": 1,
    "pitch": 2,
    "control": 3,
    "parameter": 4,
    "transport": 5,
}
SOURCE_CODES = {EventSource.HUMAN: 0, EventSource.AGENT: 1, EventSource.DAW: 2}


class ObservationBuilder:
    """Maintain active notes and encode recent DAW events with provenance."""

    def __init__(self, registry: SessionRegistry, event_capacity: int, *,
                 note_activity_from_kind: bool = False) -> None:
        if event_capacity <= 0:
            raise ValueError("Event capacity must be positive")
        # Selected snapshots already normalize velocity-zero note-ons to releases.
        # A remaining note-on may have a masked velocity of zero and is still on.
        self.note_activity_from_kind = note_activity_from_kind
        self.registry = registry
        self.event_capacity = event_capacity
        # Per track and MIDI note: active flag, onset velocity, source code.
        self._active_notes = np.zeros(
            (registry.max_tracks, 128, 3), dtype=np.float32
        )
        self._event_history: deque[DawEvent] = deque(maxlen=event_capacity)

    def reset(self) -> None:
        """Clear temporal state when a new Gymnasium episode begins."""

        self._active_notes.fill(0)
        self._event_history.clear()

    def _apply_note_state(self, event: DawEvent, track_slot: int) -> None:
        """Update held-note state from a note event while preserving its source."""

        if event.kind not in {"note_on", "note_off"}:
            return
        note = int(event.values.get("note", -1))
        if not 0 <= note < 128:
            raise ValueError(f"Invalid MIDI note in event: {note}")
        velocity = float(event.values.get("velocity", 0.0))
        is_on = event.kind == "note_on" and (velocity > 0.0 or self.note_activity_from_kind)
        self._active_notes[track_slot, note] = (
            [1.0, velocity, float(SOURCE_CODES[event.source])]
            if is_on
            else [0.0, 0.0, 0.0]
        )

    def _encode_event(self, event: DawEvent) -> np.ndarray:
        """Encode common event fields into a compact adapter-independent row."""

        if event.kind not in EVENT_KIND_CODES:
            raise ValueError(f"Unsupported event kind: {event.kind!r}")
        track_slot = self.registry.track_slot(event.track_id)
        primary = 0.0
        secondary = 0.0
        if event.kind in {"note_on", "note_off"}:
            primary = float(event.values.get("note", 0.0))
            secondary = float(event.values.get("velocity", 0.0))
        elif event.kind == "control":
            primary = float(event.values.get("control", 0.0))
            secondary = float(event.values.get("value", 0.0))
        elif event.kind == "parameter":
            primary = float(self.registry.parameter_slot(str(event.values["parameter_id"])))
            secondary = float(event.values.get("value", 0.0))
        else:
            primary = float(event.values.get("value", 0.0))

        self._apply_note_state(event, track_slot)
        return np.asarray(
            [
                event.timestamp_samples,
                track_slot,
                SOURCE_CODES[event.source],
                EVENT_KIND_CODES[event.kind],
                primary,
                secondary,
                float(event.command_id is not None),
                0.0,
            ],
            dtype=np.float64,
        )

    def build(self, snapshot: DawSnapshot) -> dict[str, np.ndarray]:
        """Build one fixed-shape observation, retaining only newest events."""

        transport = snapshot.transport
        transport_vector = np.asarray(
            [
                transport.sample_position,
                transport.sample_rate,
                transport.tempo,
                transport.beat_position,
                float(transport.playing),
            ],
            dtype=np.float64,
        )
        events = np.zeros((self.event_capacity, 8), dtype=np.float64)
        event_mask = np.zeros(self.event_capacity, dtype=np.int8)
        # Snapshots often contain only events since the previous control tick.
        # Retain a rolling history so the policy sees temporal context rather
        # than losing an event immediately on the next empty tick.
        self._event_history.extend(snapshot.events)
        recent = tuple(self._event_history)
        for row, event in enumerate(recent):
            events[row] = self._encode_event(event)
            event_mask[row] = 1

        track_mask = np.zeros(self.registry.max_tracks, dtype=np.int8)
        track_mask[: len(self.registry.tracks)] = 1
        parameter_mask = np.zeros(self.registry.max_parameters, dtype=np.int8)
        parameter_mask[: len(self.registry.parameters)] = 1
        parameter_values = np.zeros(self.registry.max_parameters, dtype=np.float32)
        parameter_valid = np.zeros(self.registry.max_parameters, dtype=np.int8)
        for parameter_id, value in snapshot.parameter_values.items():
            parameter_values[self.registry.parameter_slot(parameter_id)] = float(value)
            parameter_valid[self.registry.parameter_slot(parameter_id)] = 1

        return {
            "transport": transport_vector,
            "events": events,
            "event_mask": event_mask,
            "track_mask": track_mask,
            "active_notes": self._active_notes.copy(),
            "parameter_values": parameter_values,
            "parameter_mask": parameter_mask,
            "parameter_valid": parameter_valid,
        }
