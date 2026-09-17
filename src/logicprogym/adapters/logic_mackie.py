"""Reusable addressed-parameter bridge for Logic's Mackie Control support.

This module contains the state and allocation logic used by agents. CoreMIDI
endpoint ownership can live in a service or application and inject ordinary
Mido-compatible output ports here, which keeps the bridge deterministic in
tests and reusable outside the interactive example.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import ExitStack
from pathlib import Path
from time import sleep
from typing import Any, Callable, Sequence

import mido
import yaml

from logicprogym.adapters.mackie import (
    MackieLcd,
    button_messages,
    instrument_page,
    track_select_messages,
    vpot_message,
)
from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.adapters.mackie_feedback import MackieFeedback
from logicprogym.models import (
    DawCommand,
    DawSnapshot,
    ParameterDescriptor,
    TrackDescriptor,
)


TO_LOGIC = "LogicProGym Control To Logic"
FROM_LOGIC = "LogicProGym Control From Logic"


def mackie_endpoint_names(base: str, count: int) -> list[str]:
    """Create unique endpoint names while preserving single-device compatibility."""

    if count < 1:
        raise ValueError("Controller count must be at least 1")
    if count == 1:
        return [base]
    for suffix in (" To Logic", " From Logic"):
        if base.endswith(suffix):
            stem = base[: -len(suffix)]
            return [f"{stem} {index}{suffix}" for index in range(1, count + 1)]
    return [f"{base} {index}" for index in range(1, count + 1)]


@dataclass(frozen=True)
class LogicMackieTrack:
    """A logical agent track and its one-based slot in a Mackie bank."""

    id: str
    logic_track: int
    controller: int | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Mackie track id cannot be empty")
        if not 1 <= self.logic_track <= 8:
            raise ValueError("Logic track must be in the current Mackie bank (1-8)")
        if self.controller is not None and self.controller < 1:
            raise ValueError("Preferred Mackie controller numbers are one-based")


@dataclass(frozen=True)
class LogicMackieProfile:
    """User-authored controller and track assignments loaded from YAML."""

    controller_count: int
    tracks: tuple[LogicMackieTrack, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "LogicMackieProfile":
        """Build a profile from either a standalone or adapter YAML mapping."""

        if not isinstance(data, dict):
            raise ValueError("Logic Mackie profile must be a YAML mapping")
        count = int(data.get("controller_count", 1))
        configured = data.get("controllers", ())
        tracks = tuple(
            LogicMackieTrack(
                id=str(entry.get("id", f"track_{int(entry['track'])}")),
                logic_track=int(entry["track"]),
                controller=int(entry["controller"]),
            )
            for entry in configured
            if entry.get("track") is not None
        )
        if not tracks:
            raise ValueError("Logic Mackie profile must configure at least one track")
        if count < 1:
            raise ValueError("controller_count must be at least 1")
        return cls(count, tracks)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "LogicMackieProfile":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        # Full Gym experiment files keep Mackie settings under adapter.
        if isinstance(data, dict) and "adapter" in data:
            data = data["adapter"]
        return cls.from_mapping(data)


@dataclass(frozen=True)
class MackieParameterAddress:
    """Stable address exposed to an agent despite Mackie's modal controls."""

    track_id: str
    page: int
    slot: int

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("Parameter page must be at least 1")
        if not 1 <= self.slot <= 8:
            raise ValueError("Parameter slot must be between 1 and 8")


@dataclass(frozen=True)
class MackieRelativeAction:
    """Relative change requested for one addressed Logic parameter."""

    address: MackieParameterAddress
    steps: int

    def __post_init__(self) -> None:
        if self.steps == 0 or not -63 <= self.steps <= 63:
            raise ValueError("Relative steps must be in -63..-1 or 1..63")


@dataclass
class MackieControllerState:
    """Feedback and assignment state belonging to one virtual Mackie."""

    index: int
    output: Any
    track_id: str | None = None
    lcd: MackieLcd = field(default_factory=MackieLcd)
    use_counter: int = 0


class MackieControllerPool:
    """Allocate configured tracks across a finite set of Mackie controllers."""

    def __init__(self, outputs: Sequence[Any], tracks: Sequence[LogicMackieTrack]) -> None:
        if not outputs:
            raise ValueError("At least one Mackie output is required")
        self.controllers = [
            MackieControllerState(index=index, output=output)
            for index, output in enumerate(outputs)
        ]
        self.tracks = {track.id: track for track in tracks}
        if len(self.tracks) != len(tracks):
            raise ValueError("Logic Mackie track ids must be unique")
        preferred = [track.controller for track in tracks if track.controller is not None]
        if len(preferred) != len(set(preferred)):
            raise ValueError("Only one track can be pinned to each Mackie controller")
        if preferred and max(preferred) > len(outputs):
            raise ValueError("A track refers to a Mackie controller that does not exist")
        self._clock = 0

    def acquire(self, track_id: str) -> MackieControllerState:
        """Return the preferred, existing, free, or least-recently-used controller."""

        try:
            track = self.tracks[track_id]
        except KeyError as error:
            raise KeyError(f"Unknown Logic Mackie track {track_id!r}") from error
        if track.controller is not None:
            controller = self.controllers[track.controller - 1]
        else:
            controller = next(
                (item for item in self.controllers if item.track_id == track_id),
                next(
                    (item for item in self.controllers if item.track_id is None),
                    min(self.controllers, key=lambda item: item.use_counter),
                ),
            )
        self._clock += 1
        controller.use_counter = self._clock
        controller.track_id = track_id
        return controller


class LogicMackieBridge:
    """Translate addressed agent actions into stateful Mackie MIDI messages."""

    def __init__(
        self,
        outputs: Sequence[Any],
        tracks: Sequence[LogicMackieTrack],
        *,
        instrument_presses: int = 2,
        inter_message_delay: float = 0.0,
        restore_logic_track: int | None = None,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        if instrument_presses < 1:
            raise ValueError("instrument_presses must be positive")
        if inter_message_delay < 0:
            raise ValueError("inter_message_delay cannot be negative")
        if restore_logic_track is not None and not 1 <= restore_logic_track <= 8:
            raise ValueError("restore_logic_track must be in the current bank (1-8)")
        self.pool = MackieControllerPool(outputs, tracks)
        self.instrument_presses = instrument_presses
        self.inter_message_delay = inter_message_delay
        self.restore_logic_track = restore_logic_track
        self.sleep_fn = sleep_fn
        self.track_pages: dict[str, int] = {}
        self.track_displays: dict[str, tuple[tuple[str, str], ...]] = {}
        self.feedback = MackieFeedback([])

    def _send(self, controller: MackieControllerState, messages: Sequence[mido.Message]) -> None:
        """Send ordered protocol messages with an optional Logic settling delay."""

        for index, message in enumerate(messages):
            controller.output.send(message)
            if self.inter_message_delay and index + 1 < len(messages):
                self.sleep_fn(self.inter_message_delay)

    def _activation_messages(self, track: LogicMackieTrack) -> list[mido.Message]:
        """Build selection plus Instrument Edit restoration for one track."""

        messages = list(track_select_messages(track.logic_track - 1))
        for _ in range(self.instrument_presses):
            messages.extend(button_messages("instrument"))
        return messages

    def messages_for(self, action: MackieRelativeAction) -> tuple[int, tuple[mido.Message, ...]]:
        """Build an addressed action and return controller number plus MIDI."""

        controller = self.pool.acquire(action.address.track_id)
        track = self.pool.tracks[action.address.track_id]
        messages = self._activation_messages(track)
        current_page = self.track_pages.get(track.id)
        if current_page is None:
            if action.address.page != 1:
                raise RuntimeError(
                    f"Current page for track {track.id!r} is unknown; "
                    "receive Mackie LCD feedback before addressing another page"
                )
            current_page = 1
        page_delta = action.address.page - current_page
        page_button = "cursor_right" if page_delta > 0 else "cursor_left"
        for _ in range(abs(page_delta)):
            messages.extend(button_messages(page_button))
        messages.append(vpot_message(action.address.slot - 1, action.steps))
        self.track_pages[track.id] = action.address.page
        return controller.index + 1, tuple(messages)

    def apply_relative(self, action: MackieRelativeAction) -> int:
        """Allocate a controller, send one addressed action, and return its number."""

        self.feedback.invalidate()
        controller_number, messages = self.messages_for(action)
        controller = self.pool.controllers[controller_number - 1]
        self._send(controller, messages)
        return controller_number

    def apply_batch(self, actions: Sequence[MackieRelativeAction]) -> dict[str, int]:
        """Apply many track/parameter changes with one activation per track.

        Actions are grouped by track and page. This is the bridge operation used
        for one logical Gym step; MIDI remains serial, but redundant selection,
        mode, and page messages are eliminated.
        """

        grouped: dict[str, list[MackieRelativeAction]] = {}
        if actions:
            self.feedback.invalidate()
        for action in actions:
            grouped.setdefault(action.address.track_id, []).append(action)
        assignments: dict[str, int] = {}
        for track_id, track_actions in grouped.items():
            controller = self.pool.acquire(track_id)
            track = self.pool.tracks[track_id]
            messages = self._activation_messages(track)
            current_page = self.track_pages.get(track_id)
            first_page = min(action.address.page for action in track_actions)
            if current_page is None:
                if first_page != 1:
                    raise RuntimeError(
                        f"Current page for track {track_id!r} is unknown; "
                        "the first addressed batch page must be 1"
                    )
                current_page = 1
            for action in sorted(
                track_actions, key=lambda item: (item.address.page, item.address.slot)
            ):
                page_delta = action.address.page - current_page
                page_button = "cursor_right" if page_delta > 0 else "cursor_left"
                for _ in range(abs(page_delta)):
                    messages.extend(button_messages(page_button))
                messages.append(vpot_message(action.address.slot - 1, action.steps))
                current_page = action.address.page
            self.track_pages[track_id] = current_page
            self._send(controller, messages)
            assignments[track_id] = controller.index + 1
        if grouped and self.restore_logic_track is not None:
            # Mackie addressing changes Logic's selected channel strip. Restore
            # the musician's track after the complete agent batch so live MIDI
            # continues to play the intended instrument.
            self._send(
                self.pool.controllers[0],
                track_select_messages(self.restore_logic_track - 1),
            )
        return assignments

    def ingest(self, controller_number: int, message: mido.Message) -> bool:
        """Consume Logic feedback and update the assigned track's cached state."""

        if not 1 <= controller_number <= len(self.pool.controllers):
            raise ValueError("Unknown Mackie controller number")
        controller = self.pool.controllers[controller_number - 1]
        changed = controller.lcd.consume(message)
        self.feedback.ingest(controller_number, controller.lcd, message)
        if not changed or controller.track_id is None:
            return changed
        marker = instrument_page(controller.lcd)
        if marker is not None:
            self.track_pages[controller.track_id] = marker[0]
        self.track_displays[controller.track_id] = controller.lcd.strips
        return True

    def parameters(self, track_id: str) -> tuple[tuple[str, str], ...] | None:
        """Return the most recent eight upper/lower display cells for a track."""

        return self.track_displays.get(track_id)


class LogicMackieService:
    """Own virtual CoreMIDI endpoints and connect them to LogicMackieBridge."""

    def __init__(
        self,
        profile: LogicMackieProfile,
        *,
        midi_backend: Any = mido,
        to_logic_name: str = TO_LOGIC,
        from_logic_name: str = FROM_LOGIC,
        inter_message_delay: float = 0.1,
        restore_logic_track: int | None = None,
    ) -> None:
        self.profile = profile
        self.midi_backend = midi_backend
        self.to_logic_names = mackie_endpoint_names(to_logic_name, profile.controller_count)
        self.from_logic_names = mackie_endpoint_names(
            from_logic_name, profile.controller_count
        )
        self.inter_message_delay = inter_message_delay
        self.restore_logic_track = restore_logic_track
        self.bridge: LogicMackieBridge | None = None
        self._stack: ExitStack | None = None

    @classmethod
    def from_yaml(cls, path: str | Path, **kwargs: Any) -> "LogicMackieService":
        """Build a disconnected service from a researcher-facing YAML profile."""

        return cls(LogicMackieProfile.from_yaml(path), **kwargs)

    @property
    def connected(self) -> bool:
        return self._stack is not None

    def connect(self) -> None:
        """Create virtual endpoints and begin ingesting Logic feedback."""

        if self.connected:
            return
        stack = ExitStack()
        try:
            outputs = [
                stack.enter_context(self.midi_backend.open_output(name, virtual=True))
                for name in self.to_logic_names
            ]
            bridge = LogicMackieBridge(
                outputs,
                self.profile.tracks,
                inter_message_delay=self.inter_message_delay,
                restore_logic_track=self.restore_logic_track,
            )
            for number, name in enumerate(self.from_logic_names, start=1):
                callback = lambda message, number=number: bridge.ingest(number, message)
                stack.enter_context(
                    self.midi_backend.open_input(name, virtual=True, callback=callback)
                )
        except Exception:
            stack.close()
            raise
        self.bridge = bridge
        self._stack = stack

    def apply_relative(self, action: MackieRelativeAction) -> int:
        """Send an addressed action through the connected bridge."""

        if self.bridge is None:
            raise RuntimeError("Logic Mackie service is not connected")
        return self.bridge.apply_relative(action)

    def apply_batch(self, actions: Sequence[MackieRelativeAction]) -> dict[str, int]:
        """Send one logical multi-track Gym batch through the bridge."""

        if self.bridge is None:
            raise RuntimeError("Logic Mackie service is not connected")
        return self.bridge.apply_batch(actions)

    def close(self) -> None:
        """Close inputs and outputs, causing the virtual endpoints to disappear."""

        if self._stack is not None:
            self._stack.close()
        self._stack = None
        self.bridge = None

    def __enter__(self) -> "LogicMackieService":
        self.connect()
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


class LogicMackieAdapter(LogicProAdapter):
    """Gym-facing adapter for relative Logic plug-in parameter control."""

    capabilities = AdapterCapabilities(
        agent_output=True,
        multiple_tracks=True,
        plugin_parameters=True,
    )

    def __init__(
        self,
        profile: LogicMackieProfile,
        parameters: Sequence[ParameterDescriptor] = (),
        *,
        midi_backend: Any = mido,
        inter_message_delay: float = 0.1,
        relative_deadzone: float = 0.1,
        max_steps_per_action: int = 8,
        restore_logic_track: int | None = None,
    ) -> None:
        if not 0 <= relative_deadzone < 1:
            raise ValueError("relative_deadzone must be in [0, 1)")
        if not 1 <= max_steps_per_action <= 63:
            raise ValueError("max_steps_per_action must be in 1..63")
        self.profile = profile
        self.parameter_descriptors = tuple(parameters)
        self.relative_deadzone = relative_deadzone
        self.max_steps_per_action = max_steps_per_action
        self.feedback_bindings = []
        self.service = LogicMackieService(
            profile,
            midi_backend=midi_backend,
            inter_message_delay=inter_message_delay,
            restore_logic_track=restore_logic_track,
        )

    @classmethod
    def from_config(
        cls, config: dict[str, Any], *, midi_backend: Any = mido
    ) -> "LogicMackieAdapter":
        """Build from the adapter section of a Gym experiment YAML."""

        profile = LogicMackieProfile.from_mapping(config)
        parameters: list[ParameterDescriptor] = []
        for controller in config.get("controllers", ()):
            track_id = str(controller.get("id", f"track_{int(controller['track'])}"))
            for parameter in controller.get("parameters", ()):
                parameters.append(
                    ParameterDescriptor(
                        id=str(parameter["id"]),
                        track_id=track_id,
                        name=str(parameter.get("name", parameter["id"])),
                        minimum=float(parameter.get("minimum", 0.0)),
                        maximum=float(parameter.get("maximum", 1.0)),
                    )
                )
        result = cls(
            profile,
            parameters,
            midi_backend=midi_backend,
            inter_message_delay=float(config.get("inter_message_delay", 0.1)),
            relative_deadzone=float(config.get("relative_deadzone", 0.1)),
            max_steps_per_action=int(config.get("max_steps_per_action", 8)),
            restore_logic_track=(
                None
                if config.get("restore_logic_track") is None
                else int(config["restore_logic_track"])
            ),
        )
        # Catalog IDs conventionally encode page/slot; explicit fields also work.
        import re
        for controller in config.get('controllers', ()):
            for parameter in controller.get('parameters', ()):
                address = re.search(r'/page_(\d+)/slot_(\d+)$', parameter['id'])
                page = parameter.get('page', int(address[1]) if address else None)
                slot = parameter.get('slot', int(address[2]) if address else None)
                if page is not None and slot is not None:
                    result.feedback_bindings.append(dict(
                        id=parameter['id'], name=parameter.get('name', parameter['id']),
                        controller=controller.get('controller', 1), track=controller['track'],
                        page=page, slot=slot))
        return result

    def connect(self) -> None:
        self.service.connect()
        self.service.bridge.feedback = MackieFeedback(self.feedback_bindings)

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        tracks = tuple(
            TrackDescriptor(track.id, track.id, frozenset({"plugin_parameters"}))
            for track in self.profile.tracks
        )
        return tracks, self.parameter_descriptors

    @staticmethod
    def _scalar(command: DawCommand) -> int:
        value = command.values.get("value")
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, (int, float)):
            raise ValueError("plugin.relative requires one numeric step value")
        return int(value)

    def send(self, commands: Sequence[DawCommand]) -> None:
        batch: list[MackieRelativeAction] = []
        for command in commands:
            if command.kind == "midi.all_notes_off":
                continue
            if command.kind not in {"plugin.relative", "plugin.relative_vector"}:
                raise NotImplementedError(
                    f"Logic Mackie adapter cannot encode {command.kind!r}"
                )
            encoding = command.values.get("encoding", {})
            if command.kind == "plugin.relative":
                steps = self._scalar(command)
                if steps:
                    batch.append(
                        MackieRelativeAction(
                            MackieParameterAddress(
                                command.track_id,
                                int(encoding["page"]),
                                int(encoding["slot"]),
                            ),
                            steps,
                        )
                    )
                continue
            values = command.values.get("value")
            bindings = encoding.get("parameters", ())
            if not isinstance(values, list) or len(values) != len(bindings):
                raise ValueError(
                    "plugin.relative_vector value length must match encoding.parameters"
                )
            for value, binding in zip(values, bindings):
                amount = float(value)
                if abs(amount) <= self.relative_deadzone:
                    continue
                steps = max(1, round(abs(amount) * self.max_steps_per_action))
                steps = steps if amount > 0 else -steps
                batch.append(
                    MackieRelativeAction(
                        MackieParameterAddress(
                            command.track_id,
                            int(binding["page"]),
                            int(binding["slot"]),
                        ),
                        steps,
                    )
                )
        if batch:
            self.service.apply_batch(batch)

    def receive(self) -> DawSnapshot:
        bridge = self.service.bridge
        if bridge is None:
            raise RuntimeError("Logic Mackie adapter is not connected")
        values, readings = bridge.feedback.snapshot()
        return DawSnapshot(
            parameter_values=values,
            diagnostics={
                "parameter_readings": readings,
                "mackie_pages": dict(bridge.track_pages),
                "mackie_displays": dict(bridge.track_displays),
            }
        )

    def reset(self) -> None:
        """Do not carry accepted LCD readings across episode boundaries."""
        if self.service.bridge is not None:
            self.service.bridge.feedback.invalidate()

    def close(self) -> None:
        self.service.close()
