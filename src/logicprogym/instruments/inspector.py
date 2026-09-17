"""Python interface to the native macOS Audio Unit inspector."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logicprogym.world import ControlDescriptor, ControlKind


@dataclass(frozen=True)
class AudioUnitComponent:
    """Stable Audio Component identity returned by macOS."""

    name: str
    type: str
    subtype: str
    manufacturer: str
    version: int


@dataclass(frozen=True)
class AudioUnitParameter:
    """One public parameter exposed by a separately instantiated Audio Unit."""

    address: int
    identifier: str
    name: str
    display_name: str
    minimum: float
    maximum: float
    current_value: float
    unit: int
    unit_name: str | None
    flags: int
    value_strings: tuple[str, ...]
    group_path: tuple[str, ...]


@dataclass(frozen=True)
class AudioUnitProfile:
    """Machine-readable public interface of one Audio Unit instrument instance."""

    schema_version: int
    inspected_at: str
    live_logic_instance: bool
    component: AudioUnitComponent
    parameters: tuple[AudioUnitParameter, ...]
    factory_presets: tuple[dict[str, Any], ...]
    notes: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AudioUnitProfile":
        component = AudioUnitComponent(**raw["component"])
        parameters = tuple(
            AudioUnitParameter(
                address=parameter["address"],
                identifier=parameter["identifier"],
                name=parameter["name"],
                display_name=parameter["displayName"],
                minimum=parameter["minimum"],
                maximum=parameter["maximum"],
                current_value=parameter["currentValue"],
                unit=parameter["unit"],
                unit_name=parameter.get("unitName"),
                flags=parameter["flags"],
                value_strings=tuple(parameter.get("valueStrings") or ()),
                group_path=tuple(parameter.get("groupPath") or ()),
            )
            for parameter in raw.get("parameters", ())
        )
        return cls(
            schema_version=raw["schemaVersion"],
            inspected_at=raw["inspectedAt"],
            live_logic_instance=raw["liveLogicInstance"],
            component=component,
            parameters=parameters,
            factory_presets=tuple(raw.get("factoryPresets", ())),
            notes=tuple(raw.get("notes", ())),
        )

    def world_controls(
        self, track_id: str, *, device_id: str | None = None
    ) -> tuple[ControlDescriptor, ...]:
        """Convert public AU parameters into controls usable by a music backend."""

        controls: list[ControlDescriptor] = []
        for parameter in self.parameters:
            if parameter.value_strings:
                kind = (
                    ControlKind.BINARY
                    if len(parameter.value_strings) == 2
                    else ControlKind.DISCRETE
                )
            else:
                kind = ControlKind.CONTINUOUS
            stable_name = parameter.identifier or str(parameter.address)
            control_id = "/".join(
                part for part in (track_id, device_id, stable_name) if part
            )
            controls.append(
                ControlDescriptor(
                    id=control_id,
                    track_id=track_id,
                    device_id=device_id,
                    name=parameter.name,
                    kind=kind,
                    minimum=parameter.minimum,
                    maximum=parameter.maximum,
                    default=parameter.current_value,
                    values=parameter.value_strings,
                    # kAudioUnitParameterFlag_IsWritable is bit 1 in the AU flags.
                    writable=bool(parameter.flags & (1 << 1)),
                    metadata={
                        "au_address": parameter.address,
                        "au_identifier": parameter.identifier,
                        "au_unit": parameter.unit,
                        "au_unit_name": parameter.unit_name,
                        "group_path": list(parameter.group_path),
                        "source": "separate_audio_unit_instance",
                    },
                )
            )
        return tuple(controls)


class AudioUnitInspector:
    """Run the native helper safely without shell interpolation."""

    def __init__(self, executable: str | Path) -> None:
        self.executable = Path(executable)

    def _run(self, arguments: list[str]) -> Any:
        if not self.executable.exists():
            raise FileNotFoundError(f"Audio Unit inspector was not found: {self.executable}")
        result = subprocess.run(
            [str(self.executable), *arguments, "--compact"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Audio Unit inspector failed: {message}")
        return json.loads(result.stdout)

    def list(self, component_type: str | None = "aumu") -> tuple[AudioUnitComponent, ...]:
        """List installed Audio Units, filtering to music devices by default."""

        arguments = ["list"]
        if component_type is not None:
            arguments.extend(["--type", component_type])
        return tuple(AudioUnitComponent(**item) for item in self._run(arguments))

    def inspect(
        self,
        component_type: str,
        subtype: str,
        manufacturer: str,
        *,
        out_of_process: bool = False,
    ) -> AudioUnitProfile:
        """Instantiate one component and load its public parameter profile."""

        arguments = [
            "inspect",
            "--type",
            component_type,
            "--subtype",
            subtype,
            "--manufacturer",
            manufacturer,
        ]
        if out_of_process:
            arguments.append("--out-of-process")
        return AudioUnitProfile.from_dict(self._run(arguments))
