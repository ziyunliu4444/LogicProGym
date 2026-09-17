"""Combined Logic backend for human MIDI observation and Mackie agent control."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import mido

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.adapters.logic import LogicMidiAdapter
from logicprogym.adapters.logic_mackie import LogicMackieAdapter
from logicprogym.models import DawCommand, DawSnapshot, ParameterDescriptor, TrackDescriptor


class LogicHybridAdapter(LogicProAdapter):
    """Present Logic's MIDI and Mackie transports as one LogicProGym backend."""

    capabilities = AdapterCapabilities(
        human_events=True,
        agent_output=True,
        multiple_tracks=True,
        plugin_parameters=True,
    )

    def __init__(
        self,
        midi: LogicMidiAdapter,
        mackie: LogicMackieAdapter,
    ) -> None:
        self.midi = midi
        self.mackie = mackie
        self._connected = False

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        midi_backend: Any | None = None,
        mackie_backend: Any = mido,
    ) -> "LogicHybridAdapter":
        """Build both transports from nested ``midi`` and ``mackie`` sections."""

        if "midi" not in config or "mackie" not in config:
            raise ValueError("Logic hybrid adapter requires midi and mackie sections")
        return cls(
            LogicMidiAdapter.from_config(config["midi"], midi_backend=midi_backend),
            LogicMackieAdapter.from_config(config["mackie"], midi_backend=mackie_backend),
        )

    def connect(self) -> None:
        """Open human MIDI first, then Mackie, rolling back on partial failure."""

        if self._connected:
            return
        try:
            self.midi.connect()
            self.mackie.connect()
        except Exception:
            self.midi.close()
            self.mackie.close()
            raise
        self._connected = True

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        """Merge track capabilities and Mackie parameter descriptors."""

        midi_tracks, midi_parameters = self.midi.discover()
        mackie_tracks, mackie_parameters = self.mackie.discover()
        merged: dict[str, TrackDescriptor] = {}
        for track in (*midi_tracks, *mackie_tracks):
            previous = merged.get(track.id)
            merged[track.id] = TrackDescriptor(
                track.id,
                track.name if previous is None else previous.name,
                track.capabilities
                if previous is None
                else previous.capabilities | track.capabilities,
            )
        return tuple(merged.values()), tuple((*midi_parameters, *mackie_parameters))

    def send(self, commands: Sequence[DawCommand]) -> None:
        """Route MIDI commands and plug-in commands to their concrete transports."""

        midi_commands = [command for command in commands if command.kind.startswith("midi.")]
        plugin_commands = [
            command for command in commands if command.kind.startswith("plugin.")
        ]
        unknown = [
            command.kind
            for command in commands
            if not command.kind.startswith(("midi.", "plugin."))
        ]
        if unknown:
            raise NotImplementedError(f"Logic hybrid adapter cannot route {unknown[0]!r}")
        if midi_commands:
            self.midi.send(midi_commands)
        if plugin_commands:
            self.mackie.send(plugin_commands)

    def receive(self) -> DawSnapshot:
        """Return one snapshot containing human events and Mackie feedback state."""

        midi = self.midi.receive()
        mackie = self.mackie.receive()
        return DawSnapshot(
            transport=midi.transport,
            events=midi.events + mackie.events,
            parameter_values={**midi.parameter_values, **mackie.parameter_values},
            diagnostics={
                "midi": midi.diagnostics,
                "mackie": mackie.diagnostics,
            },
        )

    def reset(self) -> None:
        self.midi.reset()
        self.mackie.reset()

    def close(self) -> None:
        # Finish the note transport first so a stalled Mackie close cannot
        # prevent MIDI output cleanup.
        try:
            self.midi.close()
        finally:
            try:
                self.mackie.close()
            finally:
                self._connected = False
