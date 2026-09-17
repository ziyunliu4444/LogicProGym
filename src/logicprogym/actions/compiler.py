"""Compile structured Gymnasium actions into canonical DAW commands."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import uuid4

import numpy as np

from logicprogym.actions.specs import ActionRepresentation, ActionSpec
from logicprogym.models import DawCommand


def _policy_value(value: object) -> object:
    """Convert NumPy policy output into command metadata safe to serialize."""

    array = np.asarray(value)
    return array.item() if array.ndim == 0 else array.tolist()


def _semantic_value(value: object, spec: ActionSpec) -> object:
    """Validate policy output and resolve indices to researcher-defined values."""

    if spec.representation is ActionRepresentation.DISCRETE:
        array = np.asarray(value)
        if array.size != 1 or not np.issubdtype(array.dtype, np.integer):
            raise ValueError(f"Action {spec.id!r} requires one discrete index")
        index = int(array.item())
        if not 0 <= index < len(spec.values):
            raise ValueError(f"Action {spec.id!r} index {index} is out of range")
        # The policy chooses an index; adapters receive the corresponding musical
        # value (for example index 2 in a scale becomes MIDI note 64).
        return spec.values[index]

    if spec.representation is ActionRepresentation.MULTI_DISCRETE:
        indices = np.asarray(value)
        if indices.shape != (len(spec.dimensions),) or not np.issubdtype(
            indices.dtype, np.integer
        ):
            raise ValueError(
                f"Action {spec.id!r} requires {len(spec.dimensions)} discrete indices"
            )
        # Resolve each independent index, such as chord root/quality/inversion.
        selected: list[object] = []
        for index, dimension in zip(indices.tolist(), spec.dimensions):
            if not 0 <= index < len(dimension):
                raise ValueError(f"Action {spec.id!r} index {index} is out of range")
            selected.append(dimension[index])
        return selected

    # Continuous, binary, and trigger representations retain their tensor shape.
    array = np.asarray(value)
    if array.shape != spec.shape:
        raise ValueError(
            f"Action {spec.id!r} expected shape {spec.shape}, got {array.shape}"
        )
    if spec.representation is ActionRepresentation.CONTINUOUS:
        if not np.all(np.isfinite(array)):
            raise ValueError(f"Action {spec.id!r} requires finite values")
        if np.any(array < spec.low) or np.any(array > spec.high):
            raise ValueError(f"Action {spec.id!r} is outside its configured range")
    elif not np.all((array == 0) | (array == 1)):
        raise ValueError(f"Action {spec.id!r} requires binary values")
    return array.tolist()


def compile_actions(
    values: Mapping[str, object], specs: Sequence[ActionSpec]
) -> list[DawCommand]:
    """Compile a structured policy action into track-addressed commands.

    Quantization to a concrete DAW protocol is intentionally deferred to the
    adapter. This preserves the distinction between policy and wire formats.
    """

    commands: list[DawCommand] = []
    for spec in specs:
        if spec.id not in values:
            raise KeyError(f"Missing configured action: {spec.id}")
        policy_value = values[spec.id]
        semantic_value = _semantic_value(policy_value, spec)
        command_values = {
            "value": semantic_value,
            "policy_value": _policy_value(policy_value),
            "representation": spec.representation.value,
            "update_mode": spec.update_mode.value,
            "encoding": dict(spec.encoding),
        }
        if spec.target == "world.control.set":
            # World controls use a stable semantic ID rather than a MIDI/DAW
            # address. A backend decides how that ID is ultimately realized.
            command_values["control_id"] = spec.encoding.get("control_id", spec.id)
            if isinstance(semantic_value, list) and len(semantic_value) == 1:
                command_values["value"] = semantic_value[0]
        commands.append(
            DawCommand(
                track_id=spec.track_id,
                kind=spec.target,
                values=command_values,
                command_id=str(uuid4()),
            )
        )
    return commands
