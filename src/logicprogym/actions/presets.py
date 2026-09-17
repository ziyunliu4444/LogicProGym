"""Small, composable action presets.

Presets describe what the policy controls. Adapters decide whether values are
encoded as MIDI 1 integers, higher-resolution MIDI, or native plug-in values.
"""

from collections.abc import Sequence

from logicprogym.actions.specs import ActionRepresentation, ActionSpec, UpdateMode


def notes_only(track_id: str) -> tuple[ActionSpec, ...]:
    """Return polyphonic note gates plus normalized per-note velocities.

    Gates describe whether notes should currently be held. A later stateful note
    processor will turn gate edges into note-on and note-off events.
    """

    return (
        ActionSpec(
            id="note_gate",
            track_id=track_id,
            target="midi.note_gate",
            representation=ActionRepresentation.BINARY,
            shape=(128,),
            update_mode=UpdateMode.HOLD,
            encoding={"protocol": "midi", "message": "note_on_off"},
        ),
        ActionSpec(
            id="velocity",
            track_id=track_id,
            target="midi.velocity",
            representation=ActionRepresentation.CONTINUOUS,
            shape=(128,),
            encoding={"protocol": "midi1", "integer_range": [0, 127]},
        ),
    )


def discrete_pitch(
    track_id: str, pitches: Sequence[int], *, id: str = "pitch"
) -> ActionSpec:
    """Choose one pitch from an explicit chromatic, scale, or user-defined set."""
    return ActionSpec(
        id=id,
        track_id=track_id,
        target="musical.pitch",
        representation=ActionRepresentation.DISCRETE,
        values=tuple(pitches),
        encoding={"unit": "midi_note"},
    )


def continuous_pitch(
    track_id: str, low: float, high: float, *, id: str = "pitch"
) -> ActionSpec:
    """Control a gliding pitch measured in fractional MIDI-note units."""
    return ActionSpec(
        id=id,
        track_id=track_id,
        target="musical.pitch",
        representation=ActionRepresentation.CONTINUOUS,
        low=low,
        high=high,
        encoding={"unit": "midi_note"},
    )


def discrete_velocity(
    track_id: str, levels: Sequence[int], *, id: str = "velocity"
) -> ActionSpec:
    """Expose a deliberately restricted set of velocity levels to the policy."""
    return ActionSpec(
        id=id,
        track_id=track_id,
        target="midi.velocity",
        representation=ActionRepresentation.DISCRETE,
        values=tuple(levels),
        encoding={"protocol": "midi1", "integer_range": [0, 127]},
    )


def world_control(
    track_id: str,
    control_id: str,
    *,
    id: str | None = None,
    low: float = 0.0,
    high: float = 1.0,
    smoothing_ms: float = 0.0,
) -> ActionSpec:
    """Expose a backend-neutral continuous control to a policy."""

    return ActionSpec(
        id=id or control_id,
        track_id=track_id,
        target="world.control.set",
        representation=ActionRepresentation.CONTINUOUS,
        low=low,
        high=high,
        smoothing_ms=smoothing_ms,
        encoding={"control_id": control_id},
    )


def expressive_instrument(track_id: str) -> tuple[ActionSpec, ...]:
    """Add bend, expression, and sustain to polyphonic note control."""

    return notes_only(track_id) + (
        ActionSpec(
            id="pitch_bend",
            track_id=track_id,
            target="midi.pitch_bend",
            representation=ActionRepresentation.CONTINUOUS,
            low=-1.0,
            encoding={"protocol": "midi1", "integer_range": [-8192, 8191]},
        ),
        ActionSpec(
            id="expression",
            track_id=track_id,
            target="midi.cc.11",
            representation=ActionRepresentation.CONTINUOUS,
            encoding={"protocol": "midi1", "integer_range": [0, 127]},
        ),
        ActionSpec(
            id="sustain",
            track_id=track_id,
            target="midi.cc.64",
            representation=ActionRepresentation.CONTINUOUS,
            encoding={"protocol": "midi1", "integer_range": [0, 127]},
        ),
    )
