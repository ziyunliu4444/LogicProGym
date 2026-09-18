"""Catalog selection is offline, ordered, explicit, and independent of track names."""
import pytest
import yaml
from logicprogym.config import LogicProGymConfig
from logicprogym.parameter_catalog import resolve_catalogs


def session(tmp_path):
    catalog = {'tracks': {'source': {'pages': [{'page': 1, 'parameters': [
        {'slot': 1, 'name': 'Robotc'}, {'slot': 2, 'name': 'Cutoff'}]}]}}}
    (tmp_path / 'catalog.yaml').write_text(yaml.safe_dump(catalog))
    return {'adapter': {'type': 'logic_mackie', 'controller_count': 2, 'controllers': [
        {'id': 'agent', 'controller': 2, 'track': 2, 'catalog': {
            'file': 'catalog.yaml', 'track': 'source', 'select': [{'page': 1, 'slot': 2}]}}]},
        'tracks': [{'alias': 'agent', 'observe': ['plugin_parameters'], 'actions': {'mackie': True}}]}


def test_catalog_compiles_selected_names_and_vector(tmp_path):
    raw = session(tmp_path)
    path = tmp_path / 'session.yaml'
    path.write_text(yaml.safe_dump(raw))
    config = LogicProGymConfig.from_yaml(path)
    parameters = config.adapter['controllers'][0]['parameters']
    assert parameters == [dict(id='agent/page_1/slot_2', name='Cutoff', page=1, slot=2)]
    assert config.actions[0].id == 'agent/parameter_vector'
    assert config.actions[0].shape == (1,)
    assert config.actions[0].encoding['parameters'][0]['slot'] == 2
    import logicprogym
    env = logicprogym.make(path)
    try:
        assert env.action_space['agent/parameter_vector'].shape == (1,)
        # The runtime registry is populated on reset; inspect the offline
        # adapter descriptors without opening MIDI endpoints.
        assert env.unwrapped.adapter.parameter_descriptors[0].name == 'Cutoff'
    finally:
        env.close()


@pytest.mark.parametrize('selection', [None, [{'page': 1, 'slot': 9}],
    [{'page': 1, 'slot': 2}, {'page': 1, 'slot': 2}], [{'page': True, 'slot': 2}]])
def test_catalog_rejects_invalid_selection(tmp_path, selection):
    raw = session(tmp_path)
    raw['adapter']['controllers'][0]['catalog']['select'] = selection
    with pytest.raises(ValueError):
        resolve_catalogs(raw, tmp_path / 'session.yaml')


def test_discovery_does_not_implicitly_enable_actions(tmp_path):
    raw = session(tmp_path)
    raw['tracks'][0].pop('actions')
    path = tmp_path / 'session.yaml'
    path.write_text(yaml.safe_dump(raw))
    assert LogicProGymConfig.from_yaml(path).actions == ()
    raw['adapter']['controllers'][0]['parameters'] = []
    with pytest.raises(ValueError, match='not both'):
        resolve_catalogs(raw, path)


def test_public_discovery_template_needs_no_names():
    config = LogicProGymConfig.from_yaml('configs/examples/logic_discovery.yaml')
    assert not config.actions
    assert config.adapter['controllers'][0]['parameters'] == []
