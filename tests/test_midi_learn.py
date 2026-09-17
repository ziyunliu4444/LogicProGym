"""Verify the guided sender without opening hardware ports."""

import pytest
from tools import logic_midi_learn as example


def test_sweep_and_interactive_values(monkeypatch):
    messages = []

    class Port:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def send(self, message):
            messages.append(message)

    port = Port()
    monkeypatch.setattr(example.mido, 'get_output_names', lambda: ['test'])
    monkeypatch.setattr(example.mido, 'open_output', lambda name: port)
    monkeypatch.setattr(example.time, 'sleep', lambda delay: None)
    answers = iter(['', '', 'bad', '128', '64', '64', 'quit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    example.run('test', 1, 20)
    assert port.closed
    assert all(m.type == 'control_change' and m.channel == 0 and m.control == 20 for m in messages)
    assert [m.value for m in messages[-2:]] == [64, 64]
    assert min(m.value for m in messages) == 0
    assert max(m.value for m in messages) == 127


def test_cancel_before_sweep_opens_no_output(monkeypatch):
    monkeypatch.setattr(example.mido, 'get_output_names', lambda: ['test'])
    monkeypatch.setattr(example.mido, 'open_output', lambda name: pytest.fail('opened before ready'))

    def cancel(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr('builtins.input', cancel)
    with pytest.raises(KeyboardInterrupt):
        example.run('test', 1, 20)
