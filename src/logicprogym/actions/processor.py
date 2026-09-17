"""Stateful interpretation of policy controls across environment steps."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from uuid import uuid4

import numpy as np

from logicprogym.actions.compiler import compile_actions
from logicprogym.actions.specs import ActionSpec
from logicprogym.models import DawCommand


class ActionProcessor:
    """Turn held note gates into edge-triggered musical commands.

    A policy describes which notes should be active *now*. DAWs consume events,
    so this processor remembers the previous gate state and emits note-on only on
    a rising edge and note-off only on a falling edge. State is isolated by track.
    """

    def __init__(self, specs: Sequence[ActionSpec]) -> None:
        self.specs = tuple(specs)
        self._spec_by_id = {spec.id: spec for spec in self.specs}
        self._active_notes: dict[str, set[int]] = defaultdict(set)

    @staticmethod
    def _gate_pitches(spec: ActionSpec) -> tuple[int, ...]:
        """Return the pitch represented by each element of a polyphonic gate."""

        configured = spec.encoding.get("pitches")
        pitches = tuple(configured) if configured is not None else tuple(range(spec.shape[0]))
        if len(pitches) != spec.shape[0]:
            raise ValueError(
                f"Gate {spec.id!r} defines {len(pitches)} pitches for shape {spec.shape}"
            )
        return pitches

    def _velocity_for_note(
        self, track_id: str, pitch_index: int, values: Mapping[str, object]
    ) -> float:
        """Read a companion velocity action, defaulting safely when absent."""

        velocity_spec = next(
            (
                spec
                for spec in self.specs
                if spec.track_id == track_id and spec.target == "midi.velocity"
            ),
            None,
        )
        if velocity_spec is None:
            return 1.0
        raw = np.asarray(values[velocity_spec.id], dtype=np.float32)
        if raw.shape == (1,):
            return float(raw[0])
        if raw.shape != velocity_spec.shape or pitch_index >= raw.size:
            raise ValueError(f"Velocity action {velocity_spec.id!r} does not match its note gate")
        return float(raw[pitch_index])

    def process(self, values: Mapping[str, object]) -> list[DawCommand]:
        """Compile one policy step, including note edges and ordinary controls."""

        missing = [spec.id for spec in self.specs if spec.id not in values]
        if missing:
            raise KeyError(f"Missing configured action: {missing[0]}")

        commands: list[DawCommand] = []
        gate_specs = [spec for spec in self.specs if spec.target == "midi.note_gate"]
        companion_ids = {
            spec.id
            for spec in self.specs
            if spec.target == "midi.velocity"
            and any(gate.track_id == spec.track_id for gate in gate_specs)
        }

        for gate_spec in gate_specs:
            gate = np.asarray(values[gate_spec.id])
            if gate.shape != gate_spec.shape or not np.all((gate == 0) | (gate == 1)):
                raise ValueError(f"Action {gate_spec.id!r} requires a binary gate vector")

            pitches = self._gate_pitches(gate_spec)
            desired = {pitches[index] for index in np.flatnonzero(gate)}
            active = self._active_notes[gate_spec.track_id]

            # Release first so replacing a note on a monophonic destination does
            # not briefly exceed its intended polyphony.
            for pitch in sorted(active - desired):
                commands.append(
                    DawCommand(
                        track_id=gate_spec.track_id,
                        kind="midi.note_off",
                        values={"note": pitch},
                        command_id=str(uuid4()),
                    )
                )
            for pitch in sorted(desired - active):
                pitch_index = pitches.index(pitch)
                commands.append(
                    DawCommand(
                        track_id=gate_spec.track_id,
                        kind="midi.note_on",
                        values={
                            "note": pitch,
                            "velocity": self._velocity_for_note(
                                gate_spec.track_id, pitch_index, values
                            ),
                        },
                        command_id=str(uuid4()),
                    )
                )
            self._active_notes[gate_spec.track_id] = desired

        # Velocity is onset metadata when a note gate exists. Other configured
        # controls remain stateless canonical commands at this layer.
        ordinary_specs = [
            spec
            for spec in self.specs
            if spec.target != "midi.note_gate" and spec.id not in companion_ids
        ]
        commands.extend(compile_actions(values, ordinary_specs))
        return commands

    def reset(self) -> list[DawCommand]:
        """Release every tracked note and clear state for a new episode."""

        commands = [
            DawCommand(track_id=track_id, kind="midi.note_off", values={"note": note})
            for track_id, notes in sorted(self._active_notes.items())
            for note in sorted(notes)
        ]
        self._active_notes.clear()
        return commands

    def emergency_stop(self) -> list[DawCommand]:
        """Release known notes, sustain, and sound on every configured note track."""

        tracks = sorted(
            {spec.track_id for spec in self.specs if spec.target == "midi.note_gate"}
        )
        commands: list[DawCommand] = []
        for track_id in tracks:
            # Release sustain before Note Off so a pedal-held voice cannot remain.
            commands.append(
                DawCommand(track_id, "midi.cc.64", {"value": 0.0})
            )
            # Release the full MIDI pitch range. This also clears notes that a
            # DAW accepted but whose local Note On state was lost or interrupted.
            commands.extend(
                DawCommand(track_id, "midi.note_off", {"note": note})
                for note in range(128)
            )
            # CC123 is conventional cleanup; CC120 is the final hard-silence
            # fallback for instruments that ignore All Notes Off.
            commands.append(DawCommand(track_id, "midi.all_notes_off", {}))
            commands.append(DawCommand(track_id, "midi.all_sound_off", {}))
        self._active_notes.clear()
        return commands
