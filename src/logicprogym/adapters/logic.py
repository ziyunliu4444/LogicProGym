"""Routed MIDI input and output for Logic Pro.

The MIDI adapter uses configured ports and channels per exposed track. It does
not read Logic transport, mixer state, or arbitrary plug-in parameters. Mackie
parameter control and feedback are implemented separately in logic_mackie.py;
logic_hybrid.py combines the two transports.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from queue import SimpleQueue
from collections import deque
from threading import Lock
from time import monotonic, sleep
from typing import Any

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.models import (
    DawCommand,
    DawEvent,
    DawSnapshot,
    EventSource,
    ParameterDescriptor,
    TrackDescriptor,
    TransportState,
)


@dataclass(frozen=True)
class LogicMidiRoute:
    """MIDI ports and channel assigned to one Logic track.

    ``input_port`` receives observations from a configured MIDI source, such as
    a physical keyboard or virtual bus; it need not originate in Logic.
    ``output_port`` sends agent messages to a destination routed into Logic.
    ``input_source`` labels incoming events; correct routing is still required
    to prevent agent output from being mistaken for human input.
    """

    track_id: str
    name: str
    input_port: str | None = None
    output_port: str | None = None
    channel: int = 0
    input_source: EventSource = EventSource.HUMAN

    def __post_init__(self) -> None:
        if not 0 <= self.channel <= 15:
            raise ValueError("MIDI channel must be between 0 and 15")
        if self.input_port is None and self.output_port is None:
            raise ValueError("A Logic MIDI route needs an input or output port")


class LogicAdapter(LogicProAdapter):
    """Unimplemented placeholder, not the working Logic MIDI adapter.

    The factory rejects the generic ``logic`` adapter type. Use ``logic_midi``,
    ``logic_mackie``, or ``logic_hybrid`` for supported connections.
    """

    capabilities = AdapterCapabilities()

    def connect(self) -> None:
        """Reject connection through this unimplemented placeholder."""

        raise NotImplementedError("Logic Pro communication has not been implemented yet")

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        """Discover Logic tracks and mapped parameters (not implemented)."""

        raise NotImplementedError

    def receive(self) -> DawSnapshot:
        """Receive human, transport, and parameter state (not implemented)."""

        raise NotImplementedError

    def send(self, commands: Sequence[DawCommand]) -> None:
        """Send agent commands to Logic (not implemented)."""

        raise NotImplementedError

    def close(self) -> None:
        """No-op until the adapter owns an actual connection."""

        return None


class LogicMidiAdapter(LogicProAdapter):
    """Capability-limited, multi-track MIDI bridge for Logic Pro.

    This adapter can be used with macOS IAC buses or other virtual MIDI ports.
    An injectable backend keeps routing logic testable without opening hardware.
    """

    capabilities = AdapterCapabilities(
        human_events=True,
        agent_output=True,
        multiple_tracks=True,
        transport_read=False,
        mixer_parameters=False,
        plugin_parameters=False,
    )

    def __init__(
        self,
        routes: Sequence[LogicMidiRoute],
        *,
        sample_rate: float = 44_100.0,
        midi_backend: Any | None = None,
    ) -> None:
        if not routes:
            raise ValueError("LogicMidiAdapter requires at least one track route")
        if sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
        route_ids = [route.track_id for route in routes]
        input_ports = [route.input_port for route in routes if route.input_port]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("Logic MIDI track ids must be unique")
        if len(input_ports) != len(set(input_ports)):
            raise ValueError("Each observed Logic track needs a distinct input port")

        self.routes = tuple(routes)
        self.sample_rate = sample_rate
        self._mido = midi_backend
        self._inputs: list[Any] = []
        self._outputs: dict[str, Any] = {}
        self._events: SimpleQueue[DawEvent] = SimpleQueue()
        self._started_at = 0.0
        self._connected = False

    @classmethod
    def from_config(
        cls, config: dict[str, Any], *, midi_backend: Any | None = None
    ) -> "LogicMidiAdapter":
        """Construct routes from the ``adapter`` section of an experiment YAML."""

        routes = [
            LogicMidiRoute(
                track_id=str(route.get("track_id", route.get("alias"))),
                name=str(route.get("name", route.get("alias", route.get("track_id")))),
                input_port=route.get("input_port"),
                output_port=route.get("output_port"),
                channel=int(route.get("channel", 0)),
                input_source=EventSource(route.get("input_source", "human")),
            )
            for route in config.get("routes", ())
        ]
        return cls(
            routes,
            sample_rate=float(config.get("sample_rate", 44_100.0)),
            midi_backend=midi_backend,
        )

    def check_ports(self) -> dict[str, tuple[str, ...]]:
        """Report missing configured ports without changing external state."""

        backend = self._backend()
        available_inputs = set(backend.get_input_names())
        available_outputs = set(backend.get_output_names())
        return {
            "missing_inputs": tuple(
                route.input_port
                for route in self.routes
                if route.input_port and route.input_port not in available_inputs
            ),
            "missing_outputs": tuple(
                route.output_port
                for route in self.routes
                if route.output_port and route.output_port not in available_outputs
            ),
        }

    def _backend(self) -> Any:
        """Defer loading the MIDI library until this adapter is used."""

        if self._mido is None:
            try:
                import mido
            except ImportError as error:
                raise RuntimeError(
                    "MIDI dependency missing; reinstall LogicProGym: python -m pip install -e ."
                ) from error
            self._mido = mido
        return self._mido

    def _sample_position(self) -> int:
        """Estimate time for diagnostics; this is not Logic's sample clock."""

        return max(0, int((monotonic() - self._started_at) * self.sample_rate))

    def enable_frames(self, capacity):
        """Enable bounded receipt-timestamped buffering before connection."""
        self._frame_events = deque(maxlen=capacity)
        self._frame_lock = Lock()
        self._frame_drops = 0

    def _capture(self, route: LogicMidiRoute, message: Any) -> None:
        """Translate an incoming Logic MIDI message into a canonical event."""

        kind: str
        values: dict[str, float | int]
        if message.type == "note_on" and message.velocity > 0:
            kind = "note_on"
            values = {"note": message.note, "velocity": message.velocity / 127.0}
        elif message.type in {"note_off", "note_on"}:
            kind = "note_off"
            values = {"note": message.note, "velocity": 0.0}
        elif message.type == "pitchwheel":
            kind = "pitch"
            values = {"value": message.pitch / 8192.0}
        elif message.type == "control_change":
            kind = "control"
            values = {"control": message.control, "value": message.value / 127.0}
        else:
            return
        if hasattr(self, "_frame_events"):
            values["_received_monotonic"] = monotonic()
        event = DawEvent(
                timestamp_samples=self._sample_position(),
                track_id=route.track_id,
                source=route.input_source,
                kind=kind,
                values=values,
            )
        if hasattr(self, "_frame_events"):
            with self._frame_lock:
                if len(self._frame_events) == self._frame_events.maxlen:
                    self._frame_drops += 1
                self._frame_events.append(event)
        else:
            self._events.put(event)

    def connect(self) -> None:
        """Open every configured virtual MIDI route."""

        if self._connected:
            return
        backend = self._backend()
        self._started_at = monotonic()
        try:
            for route in self.routes:
                if route.input_port:
                    callback = lambda message, route=route: self._capture(route, message)
                    self._inputs.append(
                        backend.open_input(route.input_port, callback=callback)
                    )
                if route.output_port:
                    self._outputs[route.track_id] = backend.open_output(route.output_port)
        except Exception:
            self.close()
            raise
        self._connected = True

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        """Expose configured routes; plain MIDI cannot discover Logic tracks."""

        tracks = [
            TrackDescriptor(
                route.track_id,
                route.name,
                frozenset(
                    capability
                    for capability, available in {
                        "midi_input": route.input_port is not None,
                        "midi_output": route.output_port is not None,
                    }.items()
                    if available
                ),
            )
            for route in self.routes
        ]
        return tracks, []

    @staticmethod
    def _scalar(command: DawCommand) -> float:
        """Read the scalar value used by bend and CC commands."""

        value = command.values.get("value")
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, (int, float)):
            raise ValueError(f"Command {command.kind!r} requires a scalar value")
        return float(value)

    def _message(self, command: DawCommand, channel: int) -> Any:
        """Encode a supported canonical command as a MIDI 1 message."""

        backend = self._backend()
        if command.kind == "midi.note_on":
            velocity = int(round(float(command.values["velocity"]) * 127))
            return backend.Message(
                "note_on",
                note=int(command.values["note"]),
                velocity=max(1, min(127, velocity)),
                channel=channel,
            )
        if command.kind == "midi.note_off":
            return backend.Message(
                "note_off", note=int(command.values["note"]), velocity=0, channel=channel
            )
        if command.kind == "midi.all_notes_off":
            return backend.Message("control_change", control=123, value=0, channel=channel)
        if command.kind == "midi.all_sound_off":
            return backend.Message("control_change", control=120, value=0, channel=channel)
        if command.kind == "midi.pitch_bend":
            normalized = max(-1.0, min(1.0, self._scalar(command)))
            bend = min(8191, max(-8192, int(round(normalized * 8192))))
            return backend.Message("pitchwheel", pitch=bend, channel=channel)
        if command.kind.startswith("midi.cc."):
            control = int(command.kind.rsplit(".", 1)[1])
            value = int(round(max(0.0, min(1.0, self._scalar(command))) * 127))
            return backend.Message(
                "control_change", control=control, value=value, channel=channel
            )
        raise NotImplementedError(
            f"Logic MIDI adapter cannot encode {command.kind!r}; "
            "a richer Logic bridge is required"
        )

    def send(self, commands: Sequence[DawCommand]) -> None:
        """Route supported commands to their configured Logic MIDI track."""

        if not self._connected:
            raise RuntimeError("Logic MIDI adapter is not connected")
        routes = {route.track_id: route for route in self.routes}
        for command in commands:
            if command.track_id not in self._outputs:
                raise ValueError(f"Track {command.track_id!r} has no MIDI output route")
            route = routes[command.track_id]
            self._outputs[command.track_id].send(self._message(command, route.channel))

    def receive(self) -> DawSnapshot:
        """Drain events received since the previous environment observation."""

        events: list[DawEvent] = []
        if hasattr(self, "_frame_events"):
            with self._frame_lock:
                events.extend(self._frame_events)
                self._frame_events.clear()
        while not self._events.empty():
            events.append(self._events.get())
        return DawSnapshot(
            transport=TransportState(
                sample_position=self._sample_position(),
                sample_rate=self.sample_rate,
                playing=False,
            ),
            events=tuple(events),
            diagnostics={
                "clock_source": "local_monotonic_estimate",
                "sample_accurate": False,
                "queued_events": len(events),
                **({"frame_queue_dropped": self._frame_drops} if hasattr(self, "_frame_events") else {}),
            },
        )

    def close(self) -> None:
        """Close all virtual MIDI ports and clear connection state."""

        # Give panic messages sent immediately before shutdown a short window
        # to reach CoreMIDI and Logic before their output endpoints disappear.
        if self._connected and self._outputs:
            sleep(0.05)
        for port in [*self._inputs, *self._outputs.values()]:
            port.close()
        self._inputs.clear()
        self._outputs.clear()
        self._connected = False
