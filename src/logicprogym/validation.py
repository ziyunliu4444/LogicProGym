"""Preflight validation between experiment requirements and adapter features."""

from __future__ import annotations

from collections.abc import Sequence

from logicprogym.actions.specs import ActionSpec
from logicprogym.adapters.base import AdapterCapabilities


def required_capabilities(
    actions: Sequence[ActionSpec], observed_fields: Sequence[str] = ()
) -> set[str]:
    """Infer adapter capabilities required by a configured experiment."""

    required: set[str] = set()
    if actions:
        required.add("agent_output")
    if len({action.track_id for action in actions}) > 1:
        required.add("multiple_tracks")
    if any(action.target.startswith("plugin.") for action in actions):
        required.add("plugin_parameters")
    if any(action.target.startswith("mixer.") for action in actions):
        required.add("mixer_parameters")
    if any(field.startswith("human") or field in {"notes", "velocity", "controls"}
           for field in observed_fields):
        required.add("human_events")
    if any(field.startswith("transport") for field in observed_fields):
        required.add("transport_read")
    return required


def validate_capabilities(
    capabilities: AdapterCapabilities,
    actions: Sequence[ActionSpec],
    observed_fields: Sequence[str] = (),
) -> None:
    """Raise one actionable error listing every unsupported task requirement."""

    required = required_capabilities(actions, observed_fields)
    missing = sorted(
        capability for capability in required if not getattr(capabilities, capability)
    )
    if missing:
        raise ValueError(
            "Adapter does not support required capabilities: " + ", ".join(missing)
        )
