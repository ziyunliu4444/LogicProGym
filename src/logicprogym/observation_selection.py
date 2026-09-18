"""Per-track observation selection at the environment boundary.

Selection limits returned state, not MIDI routing or access to Python backend
objects. Filter before histories/frame buffers so excluded data never enters
the policy-facing state. Direct Python environments may retain legacy behavior
by omitting a selection; YAML environments always supply an explicit mapping.
"""
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace

from logicprogym.models import DawSnapshot, TransportState


OBSERVATION_FIELDS = frozenset({'notes', 'velocity', 'controls',
                               'plugin_parameters', 'transport'})


class ObservationSelection:
    """Select events and parameters using discovered ownership, never ID prefixes."""

    def __init__(self, tracks: Mapping[str, Sequence[str]]):
        self.tracks = {}
        for track, fields in tracks.items():
            if isinstance(fields, (str, bytes)) or not isinstance(fields, (list, tuple, set, frozenset)):
                raise ValueError(f'{track}: observe must be a list of observation names')
            if any(not isinstance(field, str) for field in fields):
                raise ValueError(f'{track}: observe entries must be strings')
            unknown = set(fields) - OBSERVATION_FIELDS
            if unknown:
                raise ValueError(f'{track}: unknown observe fields: {sorted(unknown)}')
            if 'velocity' in fields and 'notes' not in fields:
                raise ValueError(f'{track}: observing velocity requires notes')
            self.tracks[track] = frozenset(fields)

    def allows(self, track, field):
        return field in self.tracks.get(track, ())

    @property
    def transport_enabled(self):
        # Transport is session-wide: one explicit request enables that signal.
        return any('transport' in fields for fields in self.tracks.values())

    def parameter_ids(self, registry):
        return {p.id for p in registry.parameters
                if self.allows(p.track_id, 'plugin_parameters')}

    def snapshot(self, snapshot, registry):
        """Copy only selected signals, including the public info snapshot."""
        parameters = self.parameter_ids(registry)
        events = []
        known_tracks = {track.id for track in registry.tracks}
        owners = {p.id: p.track_id for p in registry.parameters}
        for event in snapshot.events:
            if event.track_id not in known_tracks:
                continue
            values = event.values
            if event.kind in {'note_on', 'note_off'} and self.allows(event.track_id, 'notes'):
                selected = {'note': values.get('note', -1)}
                # Keep note-on/off identity independent of hidden velocity.
                # MIDI note-on with velocity zero is a release at the boundary.
                kind = ('note_off' if event.kind == 'note_on' and values.get('velocity', 0) <= 0
                        else event.kind)
                selected['velocity'] = values.get('velocity', 0) if self.allows(event.track_id, 'velocity') else 0.0
            elif event.kind in {'pitch', 'control'} and self.allows(event.track_id, 'controls'):
                kind = event.kind
                selected = {key: values[key] for key in ('control', 'value') if key in values}
            elif (event.kind == 'parameter' and values.get('parameter_id') in parameters
                  and owners.get(values.get('parameter_id')) == event.track_id):
                kind = event.kind
                selected = {key: values[key] for key in ('parameter_id', 'value') if key in values}
            elif event.kind == 'transport' and self.allows(event.track_id, 'transport'):
                kind = event.kind
                selected = {'value': values.get('value', 0)}
            else:
                continue
            if '_received_monotonic' in values:
                selected['_received_monotonic'] = values['_received_monotonic']
            events.append(replace(event, kind=kind, values=deepcopy(selected)))

        def diagnostics(raw):
            # Explicit allowlist prevents arbitrary adapter diagnostics or stale
            # LCD pages from bypassing the selected observation channels.
            result = {key: deepcopy(raw[key]) for key in
                      ('clock_source', 'sample_accurate', 'frame_queue_dropped') if key in raw}
            if 'queued_events' in raw:
                result['queued_events'] = len(events)
            if 'parameter_readings' in raw:
                allowed_fields = {'name', 'valid', 'age_seconds', 'raw', 'value',
                                  'received_at', 'unit', 'controller', 'track', 'page', 'slot'}
                result['parameter_readings'] = {
                    key: {field: deepcopy(value) for field, value in reading.items()
                          if field in allowed_fields}
                    for key, reading in raw['parameter_readings'].items() if key in parameters}
            for key in ('midi', 'mackie'):
                if isinstance(raw.get(key), dict):
                    result[key] = diagnostics(raw[key])
            return result

        return DawSnapshot(
            transport=snapshot.transport if self.transport_enabled else TransportState(),
            events=tuple(events),
            parameter_values={key: value for key, value in snapshot.parameter_values.items()
                              if key in parameters},
            diagnostics=diagnostics(snapshot.diagnostics),
        )

    def mask(self, observation, registry):
        """Preserve fixed slots but mask unselected track/parameter data."""
        for slot, track in enumerate(registry.tracks):
            observation['track_mask'][slot] = bool(self.tracks.get(track.id))
            if not self.allows(track.id, 'notes'):
                observation['active_notes'][slot] = 0
            elif not self.allows(track.id, 'velocity'):
                observation['active_notes'][slot, :, 1] = 0
        allowed = self.parameter_ids(registry)
        for slot, parameter in enumerate(registry.parameters):
            if parameter.id not in allowed:
                for key in ('parameter_values', 'parameter_mask', 'parameter_valid'):
                    observation[key][slot] = 0
        return observation
