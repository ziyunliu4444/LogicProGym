"""Resolve explicitly selected scanned parameters before compiling a session.

Catalog paths are relative to the session YAML. Discovery never grants control:
only entries listed in ``select`` become available in the session.
"""

from pathlib import Path
import yaml


def resolve_catalogs(raw, session_path):
    adapter = raw.get('adapter', {})
    mackie = adapter.get('mackie', {}) if adapter.get('type') == 'logic_hybrid' else adapter
    controllers = mackie.get('controllers', [])
    selected = {}
    for controller in controllers:
        alias = str(controller.get('id', f"track_{controller['track']}"))
        reference = controller.get('catalog')
        if reference is None:
            continue
        if 'parameters' in controller:
            raise ValueError(f'{alias}: use catalog or inline parameters, not both')
        if not isinstance(reference, dict) or not isinstance(reference.get('select'), list):
            raise ValueError(f'{alias}: catalog requires file and an explicit select list')
        path = Path(session_path).parent / reference['file']
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        source_alias = reference.get('track', alias)
        if not isinstance(data, dict) or source_alias not in data.get('tracks', {}):
            raise ValueError(f'{alias}: catalog has no track {source_alias!r}')
        entries = {}
        for page in data['tracks'][source_alias]['pages']:
            for parameter in page['parameters']:
                address = (page['page'], parameter['slot'])
                if (type(address[0]) is not int or address[0] < 1 or
                        type(address[1]) is not int or not 1 <= address[1] <= 8):
                    raise ValueError(f'Invalid catalog address: {address}')
                if address in entries:
                    raise ValueError(f'Duplicate catalog address: {address}')
                name = parameter['name']
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f'Empty catalog name at {address}')
                entries[address] = name
        parameters = []
        seen = set()
        for item in reference['select']:
            if not isinstance(item, dict):
                raise ValueError('Each catalog selection needs page and slot')
            address = (item.get('page'), item.get('slot'))
            if any(type(value) is not int for value in address) or address not in entries:
                raise ValueError(f'{alias}: no catalog parameter at {address}')
            if address in seen:
                raise ValueError(f'{alias}: duplicate selection {address}')
            seen.add(address)
            page, slot = address
            parameters.append(dict(id=f'{alias}/page_{page}/slot_{slot}',
                                   name=entries[address], page=page, slot=slot))
        controller['parameters'] = parameters
        selected[alias] = parameters
    for track in raw.get('tracks', []):
        actions = track.get('actions')
        if not isinstance(actions, dict) or 'mackie' not in actions:
            continue
        if actions['mackie'] is not True:
            raise ValueError('actions.mackie must be true to enable selected catalog controls')
        parameters = selected.get(str(track['alias']), [])
        if not parameters:
            raise ValueError('actions.mackie requires a nonempty catalog selection for this track')
        additions = actions.setdefault('add', [])
        if any(item.get('id') == 'parameter_vector' for item in additions):
            raise ValueError('actions.mackie already generates parameter_vector')
        additions.append(dict(id='parameter_vector', target='plugin.relative_vector',
            representation='continuous', shape=[len(parameters)], range=[-1., 1.],
            encoding={'parameters': [{key: p[key] for key in ('id', 'page', 'slot')}
                                     for p in parameters]}))
    return raw
