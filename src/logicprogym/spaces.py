"""Compilation of researcher specifications into stable Gymnasium spaces."""

from collections.abc import Sequence

import numpy as np
from gymnasium import spaces

from logicprogym.actions.specs import ActionRepresentation, ActionSpec


def build_action_space(specs: Sequence[ActionSpec]) -> spaces.Dict:
    """Compile policy representations into one structured Gymnasium space.

    This function deliberately ignores DAW encoding. For example, a normalized
    continuous velocity remains a Box even when MIDI later encodes it as 0..127.
    """

    result: dict[str, spaces.Space] = {}
    for spec in specs:
        if spec.id in result:
            raise ValueError(f"Duplicate action id: {spec.id!r}")
        if spec.representation in {
            ActionRepresentation.BINARY,
            ActionRepresentation.TRIGGER,
        }:
            # Triggers and held binary states share a space but differ in their
            # temporal interpretation by the action processor.
            result[spec.id] = spaces.MultiBinary(spec.shape)
        elif spec.representation is ActionRepresentation.DISCRETE:
            result[spec.id] = spaces.Discrete(len(spec.values))
        elif spec.representation is ActionRepresentation.MULTI_DISCRETE:
            result[spec.id] = spaces.MultiDiscrete(
                np.asarray([len(dimension) for dimension in spec.dimensions])
            )
        else:
            result[spec.id] = spaces.Box(
                low=spec.low, high=spec.high, shape=spec.shape, dtype=np.float32
            )
    return spaces.Dict(result)


def build_observation_space(
    event_capacity: int, max_tracks: int, max_parameters: int
) -> spaces.Dict:
    """Create the initial fixed-capacity transport and event observation space."""

    # Gymnasium warns about infinite Box bounds, so use the largest finite float
    # where a protocol-level bound has not been selected yet.
    float_limit = np.finfo(np.float32).max
    return spaces.Dict(
        {
            "transport": spaces.Box(
                low=np.asarray([0.0, 1.0, 1.0, -float_limit, 0.0], dtype=np.float64),
                high=np.asarray(
                    [float_limit, 384_000.0, 1_000.0, float_limit, 1.0],
                    dtype=np.float64,
                ),
                dtype=np.float64,
            ),
            "events": spaces.Box(
                -float(float_limit),
                float(float_limit),
                shape=(event_capacity, 8),
                dtype=np.float64,
            ),
            "event_mask": spaces.MultiBinary(event_capacity),
            "track_mask": spaces.MultiBinary(max_tracks),
            "active_notes": spaces.Box(
                low=0.0,
                high=127.0,
                shape=(max_tracks, 128, 3),
                dtype=np.float32,
            ),
            "parameter_values": spaces.Box(
                low=-float(float_limit),
                high=float(float_limit),
                shape=(max_parameters,),
                dtype=np.float32,
            ),
            "parameter_mask": spaces.MultiBinary(max_parameters),
            "parameter_valid": spaces.MultiBinary(max_parameters),
        }
    )
