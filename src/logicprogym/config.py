"""Configuration loading for LogicProGym experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from logicprogym.actions.presets import expressive_instrument, notes_only
from logicprogym.actions.specs import ActionRepresentation, ActionSpec, UpdateMode


@dataclass(frozen=True)
class TrackConfig:
    """One researcher-facing track alias and its compiled controls."""

    alias: str
    match: dict[str, Any]
    observe: tuple[str, ...]
    actions: tuple[ActionSpec, ...]


def _custom_action(track_id: str, raw: dict[str, Any]) -> ActionSpec:
    """Compile a declarative YAML action into the canonical action schema."""

    try:
        representation = ActionRepresentation(raw["representation"])
    except KeyError as error:
        raise ValueError(f"Custom action on track {track_id!r} has no representation") from error

    update_mode = UpdateMode(raw.get("update_mode", "absolute"))
    value_range = raw.get("range", [0.0, 1.0])
    if len(value_range) != 2:
        raise ValueError(f"Action {raw.get('id')!r} range must contain [low, high]")

    return ActionSpec(
        id=str(raw["id"]),
        track_id=track_id,
        target=str(raw["target"]),
        representation=representation,
        shape=tuple(raw.get("shape", [1])),
        low=float(value_range[0]),
        high=float(value_range[1]),
        values=tuple(raw.get("values", ())),
        dimensions=tuple(tuple(items) for items in raw.get("dimensions", ())),
        update_mode=update_mode,
        smoothing_ms=float(raw.get("smoothing_ms", 0.0)),
        encoding=dict(raw.get("encoding", {})),
        metadata=dict(raw.get("metadata", {})),
    )


def _track_actions(track_id: str, raw: object) -> tuple[ActionSpec, ...]:
    """Compose an optional built-in preset with researcher-defined additions."""

    if raw is None:
        return ()
    if isinstance(raw, list):
        preset_name = None
        additions = raw
    elif isinstance(raw, dict):
        preset_name = raw.get("preset")
        additions = raw.get("add", [])
    else:
        raise ValueError(f"Track {track_id!r} actions must be a list or mapping")

    presets = {
        None: (),
        "notes_only": notes_only(track_id),
        "expressive_instrument": expressive_instrument(track_id),
    }
    if preset_name not in presets:
        raise ValueError(f"Unknown action preset {preset_name!r} on track {track_id!r}")
    actions = tuple(presets[preset_name]) + tuple(
        _custom_action(track_id, dict(action)) for action in additions
    )
    # Gymnasium Dict keys are global, while DAW control names are naturally local
    # to a track. Namespace YAML actions so two tracks can both expose "velocity".
    return tuple(
        ActionSpec(
            **{
                **action.__dict__,
                "id": f"{track_id}/{action.id}",
            }
        )
        for action in actions
    )


@dataclass(frozen=True)
class LogicProGymConfig:
    """Top-level experiment configuration loaded from YAML.

    Adapter and environment mappings retain transport-specific settings.
    Track entries compile into observation selections and typed action specs.
    """

    adapter: dict[str, Any]
    environment: dict[str, Any]
    tracks: tuple[TrackConfig, ...]

    @property
    def actions(self) -> tuple[ActionSpec, ...]:
        """Flatten actions from all configured tracks for ``LogicProEnv``."""

        return tuple(action for track in self.tracks for action in track.actions)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "LogicProGymConfig":
        """Load a UTF-8 YAML file, applying empty defaults to optional sections."""

        with Path(path).open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream) or {}
        from logicprogym.parameter_catalog import resolve_catalogs
        raw = resolve_catalogs(raw, path)
        tracks: list[TrackConfig] = []
        for track_raw in raw.get("tracks", ()):
            alias = str(track_raw["alias"])
            if not isinstance(track_raw.get("observe", []), list):
                raise ValueError(f"{alias}: observe must be a list of observation names")
            tracks.append(
                TrackConfig(
                    alias=alias,
                    match=dict(track_raw.get("match", {})),
                    observe=tuple(track_raw.get("observe", ())),
                    actions=_track_actions(alias, track_raw.get("actions")),
                )
            )

        aliases = [track.alias for track in tracks]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Track aliases must be unique")

        from logicprogym.observation_selection import ObservationSelection
        ObservationSelection({track.alias: track.observe for track in tracks})

        return cls(
            adapter=dict(raw.get("adapter", {})),
            environment=dict(raw.get("environment", {})),
            tracks=tuple(tracks),
        )
