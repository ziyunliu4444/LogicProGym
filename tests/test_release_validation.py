from logicprogym.logic_setup import compare_catalog
from logicprogym.control_setup import parameter_bindings
from logicprogym.config import LogicProGymConfig


def test_names_at_wrong_slots_are_rejected():
    bindings = [{'page': 1, 'slot': 2, 'name': 'Cutoff'}]
    wrong = [{'page': 1, 'parameters': [{'slot': 1, 'name': 'Cutoff'}, {'slot': 2, 'name': 'Fine'}]}]
    assert compare_catalog(bindings, wrong)
    assert not compare_catalog(bindings, [{'page': 1, 'parameters': [{'slot': 2, 'name': ' Cutoff '}]}])
    assert compare_catalog(bindings, [{'page': 2, 'parameters': [{'slot': 2, 'name': 'Cutoff'}]}])


def test_binding_names_resolve_from_configuration():
    config = LogicProGymConfig.from_yaml('configs/examples/logic_two_agents.yaml')
    assert parameter_bindings(config, 'synth') == [{'page': 1, 'slot': 2, 'name': 'Cutoff'}]
