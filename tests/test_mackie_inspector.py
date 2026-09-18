"""Inspector commands and automatic discovery with simulated LCD feedback."""
from types import SimpleNamespace as NS
import pytest
from logicprogym.adapters.mackie import MackieLcd
from logicprogym import mackie_inspector as inspector, logic_setup


def fake_component():
    sent = []
    lcd = MackieLcd()
    lcd.apply(0, 'Track 2 "Synth" "Alchemy" Page 1/2'.ljust(56))
    lcd.apply(56, 'Cutoff '.ljust(56))
    controller = NS(lcd=lcd, output=NS(send=sent.append))
    bridge = NS(pool=NS(tracks={'agent': NS(logic_track=2)}),
                feedback=NS(invalidate=lambda: None))
    return NS(service=NS(bridge=bridge)), controller, sent


def test_console_displays_without_unsolicited_vpot(monkeypatch):
    component, controller, sent = fake_component()
    monkeypatch.setattr(inspector, 'activate_parameter_view', lambda *a, **k: controller)
    commands = iter(['lcd', 'vpot 9 1', 'vpot 2 64', 'bad', 'quit'])
    output = []
    inspector.run_console(component, 'agent', read=lambda _: next(commands), emit=output.append)
    assert sent == []
    assert any('Cached Logic LCD' in line for line in output)


def test_startup_detection_failure_still_accepts_lcd(monkeypatch):
    component, controller, sent = fake_component()
    component.service.bridge.pool.acquire = lambda _: controller
    def fail(*args, **kwargs):
        raise RuntimeError('Instrument header unavailable')
    monkeypatch.setattr(inspector, 'activate_parameter_view', fail)
    commands = iter(['lcd', 'quit'])
    output = []
    inspector.run_console(component, 'agent', read=lambda _: next(commands), emit=output.append)
    assert sum('Cached Logic LCD' in line for line in output) == 2
    assert any('Console remains available' in line for line in output)
    assert sent == []


def test_console_explicit_knob_and_navigation(monkeypatch):
    component, controller, sent = fake_component()
    monkeypatch.setattr(inspector, 'activate_parameter_view', lambda *a, **k: controller)
    commands = iter(['right', 'left', 'vpot 2 1', 'quit'])
    inspector.run_console(component, 'agent', read=lambda _: next(commands),
                          emit=lambda _: None, settle=lambda _: None)
    pots = [message for message in sent if message.type == 'control_change']
    assert len(pots) == 1 and pots[0].control == 17 and pots[0].value == 1


def test_value_view_can_be_inspected_and_browsed_without_strict_activation(monkeypatch):
    component, controller, sent = fake_component()
    controller.lcd.apply(0, ''.join(name.ljust(7) for name in
        ['Robotc', 'Cutoff', 'Arp Md', 'Thin', 'Porto', 'Res', 'ArpRat', 'ArpOct']))
    controller.lcd.apply(56, ''.join(value.ljust(7) for value in
        ['46.47%', '31.47%', 'Down', '48.86%', '23.82%', '5.46 %', '1/16T', '35.12%']))
    def activate(*args, **kwargs):
        assert not kwargs.get('scan', False)
        return controller
    monkeypatch.setattr(inspector, 'activate_parameter_view', activate)
    commands = iter(['lcd', 'right', 'vpot 2 1', 'quit'])
    output = []
    inspector.run_console(component, 'agent', read=lambda _: next(commands),
                          emit=output.append, settle=lambda _: None)
    assert any('31.47%' in line for line in output)
    assert any('no knob command sent' in line for line in output)
    assert sent and all(message.type != 'control_change' for message in sent)


def test_value_view_activation_does_not_toggle_instrument(monkeypatch):
    component, controller, sent = fake_component()
    component.parameter_descriptors = [NS(track_id='agent', name='Cutoff')]
    component.service.bridge.pool.acquire = lambda _: controller
    controller.lcd.apply(0, 'Robotc Cutoff '.ljust(56))
    controller.lcd.apply(56, '46.47% 31.47% '.ljust(56))
    monkeypatch.setattr(logic_setup, '_wait_until', lambda *args: True)
    monkeypatch.setattr(logic_setup, '_wait_stable_view', lambda c, p, t: p())
    monkeypatch.setattr(logic_setup.time, 'sleep', lambda _: None)
    assert logic_setup.activate_parameter_view(component, 'agent') is controller
    from logicprogym.adapters.mackie import track_select_messages
    assert sent == list(track_select_messages(1))


def test_all_pages_uses_reported_total(monkeypatch):
    component, controller, sent = fake_component()
    monkeypatch.setattr(logic_setup, 'activate_parameter_view', lambda *a, **k: controller)
    monkeypatch.setattr(logic_setup, '_wait_stable_view', lambda c, p, t: p())
    monkeypatch.setattr(logic_setup.time, 'sleep', lambda _: None)
    def advance(output, messages):
        controller.lcd.apply(0, 'Track 2 "Synth" "Alchemy" Page 2/2'.ljust(56))
        controller.lcd.apply(56, 'Attack '.ljust(56))
    monkeypatch.setattr(logic_setup, 'send_all', advance)
    pages = logic_setup.scan_parameters(component, 'agent', pages=None)
    assert [page['page'] for page in pages] == [1, 2]
    assert pages[1]['parameters'][0]['name'] == 'Attack'


def test_all_pages_requires_total(monkeypatch):
    component, controller, _ = fake_component()
    controller.lcd.apply(0, 'Track 2 "Synth" "Alchemy" Pag'.ljust(56))
    monkeypatch.setattr(logic_setup, 'activate_parameter_view', lambda *a, **k: controller)
    with pytest.raises(RuntimeError, match='total page count'):
        logic_setup.scan_parameters(component, 'agent', pages=None)


@pytest.mark.parametrize('exception', [EOFError, KeyboardInterrupt])
def test_inspector_closes_without_reset(monkeypatch, exception):
    import logicprogym
    calls = []
    component = NS(connect=lambda: calls.append('connect'), close=lambda: calls.append('disconnect'))
    env = NS(close=lambda: calls.append('close'))
    monkeypatch.setattr(logicprogym, 'make', lambda _: env)
    monkeypatch.setattr(inspector, 'mackie_adapter', lambda _: component)
    def interrupted(*args):
        raise exception()
    monkeypatch.setattr(inspector, 'run_console', interrupted)
    assert inspector.inspect_session('unused', 'agent') == 0
    assert calls == ['connect', 'disconnect', 'close']


def test_scan_failure_closes_endpoints_without_reset(monkeypatch, tmp_path):
    from logicprogym import cli
    component, _, _ = fake_component()
    calls = []
    component.connect = lambda: calls.append('connect')
    component.close = lambda: calls.append('disconnect')
    monkeypatch.setattr(cli, 'make', lambda _: NS(close=lambda: calls.append('close')))
    monkeypatch.setattr(logic_setup, 'mackie_adapter', lambda _: component)
    def failure(*args, **kwargs):
        raise RuntimeError('No header')
    monkeypatch.setattr(logic_setup, 'scan_parameters', failure)
    destination = tmp_path / 'catalog.yaml'
    with pytest.raises(RuntimeError, match='No header'):
        cli.logic_scan('unused', 'agent', None, destination)
    assert calls == ['connect', 'disconnect', 'close']
    assert not destination.exists()
