"""Public access to selected parameter feedback returned by an environment."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterReading:
    """One parameter's last display text and independently validated number.

    ``raw`` may be historical or unverified. ``age_seconds`` measures time since
    that text was received. ``value`` is available only when ``valid`` is true;
    its units follow the parameter observation contract, not always 0–1.
    """

    id: str
    name: str
    raw: str | None
    age_seconds: float | None
    value: float | None
    valid: bool


def parameter_readings(info: Mapping) -> dict[str, ParameterReading]:
    """Read parameter feedback from reset/step info, without polling devices.

    Supports Mackie-only and hybrid sessions. Only parameters selected by the
    environment are returned; unavailable readings have ``raw``/``value`` None.
    Missing feedback yields an empty dictionary. Results describe this info
    snapshot and do not refresh when more device messages arrive.
    """
    snapshot = info.get('snapshot')
    diagnostics = {} if snapshot is None else snapshot.diagnostics
    feedback = diagnostics.get('mackie', diagnostics).get('parameter_readings', {})
    result = {}
    for parameter_id, reading in feedback.items():
        has_display = reading.get('display_raw') is not None
        valid = bool(reading.get('valid', False)) and reading.get('value') is not None
        result[parameter_id] = ParameterReading(
            id=parameter_id, name=reading.get('name', parameter_id),
            raw=reading.get('display_raw') if has_display else reading.get('raw'),
            age_seconds=reading.get('display_age_seconds') if has_display else reading.get('age_seconds'),
            value=float(reading['value']) if valid else None, valid=valid)
    return result
