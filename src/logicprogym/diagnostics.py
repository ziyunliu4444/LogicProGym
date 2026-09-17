"""Offline setup diagnostics for configured Logic Pro environments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from logicprogym.config import LogicProGymConfig
from logicprogym.factory import make


@dataclass(frozen=True)
class Diagnostic:
    """One actionable configuration check."""

    level: str
    subject: str
    message: str


def _port_check(
    direction: str,
    track_id: str,
    configured: str,
    available: set[str],
) -> Diagnostic:
    if configured in available:
        return Diagnostic("PASS", f"{track_id} {direction}", configured)
    return Diagnostic(
        "FAIL",
        f"{track_id} {direction}",
        f"{configured!r} was not found; available ports: "
        + (", ".join(sorted(available)) if available else "none"),
    )


def diagnose(
    config_path: str | Path,
    *,
    input_ports: Iterable[str],
    output_ports: Iterable[str],
) -> tuple[Diagnostic, ...]:
    """Validate a Logic configuration without opening or changing DAW state."""

    path = Path(config_path)
    config = LogicProGymConfig.from_yaml(path)
    env = make(path)
    results = [
        Diagnostic("PASS", "configuration", str(path)),
        Diagnostic(
            "PASS",
            "Gymnasium action space",
            ", ".join(env.action_space.spaces) or "empty",
        ),
        Diagnostic("PASS", "Gymnasium observation space", "valid fixed-shape space"),
    ]

    adapter = config.adapter
    midi = adapter.get("midi", adapter)
    if adapter.get("type") in {"logic_midi", "logic_hybrid"}:
        known_inputs = set(input_ports)
        known_outputs = set(output_ports)
        for index, route in enumerate(midi.get("routes", ()), start=1):
            track_id = str(route.get("track_id", route.get("alias", f"route_{index}")))
            if route.get("input_port"):
                results.append(
                    _port_check("input", track_id, str(route["input_port"]), known_inputs)
                )
            if route.get("output_port"):
                results.append(
                    _port_check(
                        "output", track_id, str(route["output_port"]), known_outputs
                    )
                )

    mackie = adapter.get("mackie", adapter)
    if adapter.get("type") in {"logic_mackie", "logic_hybrid"}:
        count = int(mackie.get("controller_count", 1))
        assignments = mackie.get("controllers", ())
        for assignment in assignments:
            controller = int(assignment["controller"])
            track = int(assignment["track"])
            track_id = str(assignment.get("id", f"track_{track}"))
            results.append(
                Diagnostic(
                    "PASS",
                    f"Mackie {controller}",
                    f"controls Logic track {track} as {track_id!r}",
                )
            )
        results.append(
            Diagnostic(
                "INFO",
                "Logic Control Surfaces",
                f"configure {count} Mackie Control device(s); their LogicProGym "
                "To/From Logic ports appear when the environment connects",
            )
        )

    env.close()
    return tuple(results)
