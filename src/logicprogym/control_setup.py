"""Validate per-track transport choices before opening any MIDI ports."""

def validate_routes(config):
    adapter = config.adapter
    kind = adapter.get('type')
    if kind not in {'logic_midi', 'logic_mackie', 'logic_hybrid'}:
        return
    midi = adapter.get('midi', adapter) if kind != 'logic_mackie' else {}
    mackie = adapter.get('mackie', adapter) if kind != 'logic_midi' else {}
    routes = {r.get('track_id', r.get('alias')): r for r in midi.get('routes', ())}
    controllers = {r.get('id', f"track_{r['track']}"): r for r in mackie.get('controllers', ())}
    for track in config.tracks:
        for action in track.actions:
            # Custom names are welcome, but their transport targets must exist.
            supported = {'midi.note_gate', 'midi.velocity', 'midi.pitch_bend',
                         'midi.note_on', 'midi.note_off', 'midi.all_notes_off',
                         'midi.all_sound_off', 'plugin.relative', 'plugin.relative_vector'}
            cc = action.target.removeprefix('midi.cc.')
            valid_cc = action.target.startswith('midi.cc.') and cc.isdigit() and 0 <= int(cc) <= 127
            if action.target not in supported and not valid_cc:
                raise ValueError(f'{action.id}: unsupported Logic action target {action.target!r}')
            if action.target.startswith('midi.') and not routes.get(track.alias, {}).get('output_port'):
                raise ValueError(f'{action.id}: MIDI control requires an output_port for track {track.alias!r}')
            if action.target.startswith('plugin.') and track.alias not in controllers:
                raise ValueError(f'{action.id}: parameter control requires a Mackie assignment for track {track.alias!r}')
            if action.target in {'plugin.relative', 'plugin.relative_vector'}:
                bindings = (action.encoding,) if action.target == 'plugin.relative' else action.encoding.get('parameters', ())
                if not bindings:
                    raise ValueError(f'{action.id}: missing parameter bindings')
                if action.target == 'plugin.relative_vector' and action.shape != (len(bindings),):
                    raise ValueError(f'{action.id}: vector shape must match parameter bindings')
                for binding in bindings:
                    page, slot = binding.get('page'), binding.get('slot')
                    if not isinstance(page, int) or page < 1 or not isinstance(slot, int) or not 1 <= slot <= 8:
                        raise ValueError(f'{action.id}: page must be positive and slot must be 1..8')


def parameter_bindings(config, track_id):
    """Resolve action addresses to declared display names without guessing IDs."""
    settings = config.adapter.get('mackie', config.adapter)
    entry = next(c for c in settings['controllers'] if c.get('id', f"track_{c['track']}") == track_id)
    names = {p['id']: p['name'] for p in entry.get('parameters', ()) if p.get('name')}
    found = []
    for action in config.actions:
        if action.track_id != track_id:
            continue
        if action.target == 'plugin.relative_vector':
            bindings = action.encoding['parameters']
        elif action.target == 'plugin.relative':
            bindings = [action.encoding]
        else:
            continue
        for binding in bindings:
            name = binding.get('name') or names.get(binding.get('id'))
            if not name:
                raise ValueError(f'{action.id}: live verification requires an explicit parameter id/name')
            found.append(dict(page=binding['page'], slot=binding['slot'], name=name))
    return found


def preview(config_path):
    """Return an offline description of the actual configured action space."""
    from logicprogym.config import LogicProGymConfig
    from logicprogym.factory import make
    config = LogicProGymConfig.from_yaml(config_path)
    env = make(config_path)
    try:
        lines = ['Control preview (no MIDI ports opened)']
        for track in config.tracks:
            midi = any(a.target.startswith('midi.') for a in track.actions)
            mackie = any(a.target.startswith('plugin.') for a in track.actions)
            mode = 'MIDI + Mackie' if midi and mackie else 'MIDI' if midi else 'Mackie' if mackie else 'observation only'
            lines.append(f'{track.alias}: {mode}; observe={list(track.observe)}')
            for action in track.actions:
                lines.append(f'  {action.id} -> {action.target}: {env.action_space.spaces[action.id]}')
                for binding in action.encoding.get('parameters', ()):
                    lines.append(f"    {binding['id']}: page {binding['page']}, slot {binding['slot']}")
        return '\n'.join(lines)
    finally:
        env.close()
