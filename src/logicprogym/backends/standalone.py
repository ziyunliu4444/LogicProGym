"""Deterministic in-process music world for training, tests, and prototyping."""

from __future__ import annotations

from collections.abc import Sequence

from logicprogym.backends.base import BackendCapabilities, MusicBackend
from logicprogym.models import (
    DawCommand,
    DawEvent,
    DawSnapshot,
    EventSource,
    TransportState,
)
from logicprogym.world import (
    AccessPolicy,
    ConflictPolicy,
    ControlDescriptor,
    MusicWorldDescription,
)


class StandaloneBackend(MusicBackend):
    """Run a shared event/control world without requiring a DAW or audio device.

    It intentionally does not implement a full audio workstation. Its purpose is
    deterministic interaction with the same tracks and controls used by a live
    backend. A renderer or learned surrogate can be attached later.
    """

    capabilities = BackendCapabilities(
        human_events=True,
        agent_output=True,
        multiple_tracks=True,
        transport_read=True,
        mixer_parameters=True,
        plugin_parameters=True,
        audio_features=False,
        deterministic_reset=True,
    )

    def __init__(
        self,
        world: MusicWorldDescription,
        *,
        sample_rate: float = 44_100.0,
        block_size: int = 512,
        tempo: float = 120.0,
    ) -> None:
        if sample_rate <= 0 or block_size <= 0 or tempo <= 0:
            raise ValueError("Sample rate, block size, and tempo must be positive")
        self.world = world
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.tempo = tempo
        self._controls = {control.id: control for control in world.controls}
        if len(self._controls) != len(world.controls):
            raise ValueError("World control identifiers must be unique")
        self._track_ids = {track.id for track in world.tracks}
        self._connected = False
        self._sample_position = 0
        self._events: list[DawEvent] = []
        self._control_values: dict[str, float] = {}
        self._last_writer: dict[str, EventSource] = {}
        self._last_write_position: dict[str, int] = {}
        self.reset()

    def connect(self) -> None:
        self._connected = True

    def discover_world(self) -> MusicWorldDescription:
        return self.world

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("Standalone music world is not connected")

    def _check_track(self, track_id: str) -> None:
        if track_id not in self._track_ids:
            raise KeyError(f"Unknown music-world track: {track_id!r}")

    @staticmethod
    def _allowed(control: ControlDescriptor, source: EventSource) -> bool:
        if control.access is AccessPolicy.SHARED:
            return True
        if control.access is AccessPolicy.HUMAN_ONLY:
            return source is EventSource.HUMAN
        if control.access is AccessPolicy.AGENT_ONLY:
            return source is EventSource.AGENT
        return False

    def _set_control(
        self,
        control_id: str,
        requested_value: float,
        source: EventSource,
        command_id: str | None = None,
    ) -> None:
        """Apply access and conflict rules, then publish one parameter event."""

        try:
            control = self._controls[control_id]
        except KeyError as error:
            raise KeyError(f"Unknown music-world control: {control_id!r}") from error
        if not control.writable or not self._allowed(control, source):
            raise PermissionError(
                f"{source.value} cannot write control {control_id!r} "
                f"with access policy {control.access.value!r}"
            )
        if (
            control.conflict is ConflictPolicy.HUMAN_PRIORITY
            and source is EventSource.AGENT
            and self._last_writer.get(control_id) is EventSource.HUMAN
            and self._last_write_position.get(control_id) == self._sample_position
        ):
            # Human priority applies only to simultaneous changes at this world
            # timestamp; it does not permanently lock the agent out.
            return

        previous = self._control_values[control_id]
        if control.conflict is ConflictPolicy.ADDITIVE:
            value = previous + requested_value
        elif control.conflict is ConflictPolicy.BLEND:
            weight = float(control.metadata.get("agent_weight", 0.5))
            if source is EventSource.AGENT:
                value = previous * (1.0 - weight) + requested_value * weight
            else:
                value = requested_value * (1.0 - weight) + previous * weight
        else:
            value = requested_value
        value = max(control.minimum, min(control.maximum, value))
        self._control_values[control_id] = value
        self._last_writer[control_id] = source
        self._last_write_position[control_id] = self._sample_position
        self._events.append(
            DawEvent(
                timestamp_samples=self._sample_position,
                track_id=control.track_id,
                source=source,
                kind="parameter",
                values={"parameter_id": control_id, "value": value},
                command_id=command_id,
            )
        )

    def _publish_musical_command(
        self, command: DawCommand, source: EventSource
    ) -> None:
        """Translate canonical MIDI commands into source-aware world events."""

        self._check_track(command.track_id)
        if command.kind in {"midi.all_notes_off", "midi.all_sound_off"}:
            control = 123 if command.kind == "midi.all_notes_off" else 120
            self._events.append(
                DawEvent(
                    self._sample_position,
                    command.track_id,
                    source,
                    "control",
                    {"control": control, "value": 0.0},
                    command.command_id,
                )
            )
            return
        if command.kind.startswith("midi."):
            event_kind = command.kind.removeprefix("midi.")
            if event_kind in {"note_on", "note_off", "pitch"}:
                self._events.append(
                    DawEvent(
                        self._sample_position,
                        command.track_id,
                        source,
                        event_kind,
                        dict(command.values),
                        command.command_id,
                    )
                )
                return
            if event_kind.startswith("cc."):
                self._events.append(
                    DawEvent(
                        self._sample_position,
                        command.track_id,
                        source,
                        "control",
                        {
                            "control": int(event_kind.rsplit(".", 1)[1]),
                            "value": command.values["value"],
                        },
                        command.command_id,
                    )
                )
                return
        raise NotImplementedError(f"Standalone world cannot apply {command.kind!r}")

    def apply(self, commands: Sequence[DawCommand]) -> None:
        """Apply agent commands at the current deterministic world timestamp."""

        self._require_connected()
        for command in commands:
            if command.kind == "world.control.set":
                self._set_control(
                    str(command.values["control_id"]),
                    float(command.values["value"]),
                    EventSource.AGENT,
                    command.command_id,
                )
            else:
                self._publish_musical_command(command, EventSource.AGENT)

    def set_human_control(self, control_id: str, value: float) -> None:
        """Inject a control manipulation made by a human participant."""

        self._require_connected()
        self._set_control(control_id, value, EventSource.HUMAN)

    def inject_human_event(
        self, track_id: str, kind: str, values: dict[str, object]
    ) -> None:
        """Inject a human musical event into the same shared timeline."""

        self._require_connected()
        self._check_track(track_id)
        self._events.append(
            DawEvent(
                self._sample_position,
                track_id,
                EventSource.HUMAN,
                kind,
                dict(values),
                command_id=None,
            )
        )

    def observe(self) -> DawSnapshot:
        """Return current events/state and advance exactly one processing block."""

        self._require_connected()
        beat_position = (
            self._sample_position / self.sample_rate * self.tempo / 60.0
        )
        snapshot = DawSnapshot(
            transport=TransportState(
                sample_position=self._sample_position,
                sample_rate=self.sample_rate,
                tempo=self.tempo,
                beat_position=beat_position,
                playing=True,
            ),
            events=tuple(self._events),
            parameter_values=dict(self._control_values),
            diagnostics={
                "clock_source": "deterministic_standalone",
                "sample_accurate": True,
                "block_size": self.block_size,
            },
        )
        self._events.clear()
        self._sample_position += self.block_size
        return snapshot

    def reset(self) -> None:
        """Restore time, events, and every control to its declared default."""

        self._sample_position = 0
        self._events.clear()
        self._control_values = {
            control.id: control.default for control in self.world.controls
        }
        self._last_writer.clear()
        self._last_write_position.clear()

    def close(self) -> None:
        self._events.clear()
        self._connected = False
