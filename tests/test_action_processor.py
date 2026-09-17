"""Temporal tests for translating held policy state into DAW note events."""

import numpy as np

from logicprogym.actions.presets import notes_only
from logicprogym.actions.processor import ActionProcessor


def _action(*active_notes: int, velocity: float = 0.75) -> dict[str, np.ndarray]:
    """Build one polyphonic policy action for concise transition tests."""

    gate = np.zeros(128, dtype=np.int8)
    gate[list(active_notes)] = 1
    velocities = np.full(128, velocity, dtype=np.float32)
    return {"note_gate": gate, "velocity": velocities}


def test_note_events_are_emitted_only_on_gate_edges():
    processor = ActionProcessor(notes_only("agent"))

    first = processor.process(_action(60))
    held = processor.process(_action(60))
    released = processor.process(_action())

    assert [(command.kind, command.values) for command in first] == [
        ("midi.note_on", {"note": 60, "velocity": 0.75})
    ]
    assert held == []
    assert [(command.kind, command.values) for command in released] == [
        ("midi.note_off", {"note": 60})
    ]


def test_note_state_is_independent_for_each_track():
    specs = notes_only("bass") + tuple(
        spec.__class__(
            **{
                **spec.__dict__,
                "id": f"lead_{spec.id}",
                "track_id": "lead",
            }
        )
        for spec in notes_only("lead")
    )
    processor = ActionProcessor(specs)
    values = {
        **_action(36),
        "lead_note_gate": _action(72)["note_gate"],
        "lead_velocity": _action(72, velocity=0.5)["velocity"],
    }

    commands = processor.process(values)
    assert [(command.track_id, command.values["note"]) for command in commands] == [
        ("bass", 36),
        ("lead", 72),
    ]


def test_reset_releases_active_notes_and_emergency_stop_targets_every_track():
    processor = ActionProcessor(notes_only("agent"))
    processor.process(_action(60, 64))

    releases = processor.reset()
    assert [command.values["note"] for command in releases] == [60, 64]
    panic = processor.emergency_stop()
    assert panic[0].kind == "midi.cc.64"
    assert [command.kind for command in panic[1:129]] == ["midi.note_off"] * 128
    assert [command.kind for command in panic[-2:]] == [
        "midi.all_notes_off",
        "midi.all_sound_off",
    ]


def test_emergency_stop_explicitly_releases_every_active_note():
    processor = ActionProcessor(notes_only("agent"))
    processor.process(_action(60, 64))
    commands = processor.emergency_stop()
    assert commands[0].kind == "midi.cc.64"
    assert [command.kind for command in commands[1:129]] == ["midi.note_off"] * 128
    assert [command.kind for command in commands[-2:]] == [
        "midi.all_notes_off",
        "midi.all_sound_off",
    ]
    assert [
        command.values["note"] for command in commands if command.kind == "midi.note_off"
    ] == list(range(128))
