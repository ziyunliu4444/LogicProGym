"""Contract tests for the generic Gymnasium environment lifecycle."""

from collections.abc import Sequence
import threading
import pytest

from gymnasium.utils.env_checker import check_env

from logicprogym.actions.presets import expressive_instrument
from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter
from logicprogym.env import LogicProEnv
from logicprogym.models import DawCommand, DawSnapshot, ParameterDescriptor, TrackDescriptor


class DummyAdapter(LogicProAdapter):
    """Minimal in-memory adapter used without pretending to be a real DAW."""

    capabilities = AdapterCapabilities(
        human_events=True, agent_output=True, multiple_tracks=True
    )

    def __init__(self):
        self.commands: list[DawCommand] = []

    def connect(self):
        pass

    def discover(self) -> tuple[Sequence[TrackDescriptor], Sequence[ParameterDescriptor]]:
        return [TrackDescriptor("agent", "Agent")], []

    def receive(self):
        return DawSnapshot()

    def send(self, commands):
        self.commands.extend(commands)

    def close(self):
        pass


def test_generic_environment_conforms_to_gymnasium():
    """The public environment must satisfy Gymnasium's standard checker."""

    env = LogicProEnv(DummyAdapter(), expressive_instrument("agent"))
    check_env(env, skip_render_check=True)
    env.close()


def test_repeated_open_play_close_same_environment():
    """A successful shutdown must allow reuse without retaining held notes."""
    env = LogicProEnv(DummyAdapter(), expressive_instrument('agent'))
    for _ in range(5):
        env.reset()
        env.step(env.action_space.sample())
        env.close()
        env.close()  # Cleanup is also idempotent.


def test_close_attempts_ports_even_if_panic_fails():
    class FailedPanic(DummyAdapter):
        closed = False

        def send(self, commands):
            raise OSError("disconnected output")

        def close(self):
            self.closed = True

    adapter = FailedPanic()
    env = LogicProEnv(adapter, expressive_instrument("agent"))
    env.reset()
    with pytest.raises(RuntimeError, match="cleanup failed"):
        env.close()
    assert adapter.closed


def test_stalled_close_returns_and_blocks_reconnection():
    release = threading.Event()

    class StalledAdapter(DummyAdapter):
        def close(self):
            release.wait()

    env = LogicProEnv(StalledAdapter(), expressive_instrument("agent"))
    env.reset()
    try:
        with pytest.raises(TimeoutError):
            env.close(timeout=0.02)
        with pytest.raises(RuntimeError, match="cleanup is still running"):
            env.reset()
        with pytest.raises(RuntimeError, match="disconnected"):
            env.step({})
    finally:
        release.set()
        env.close()
    env.reset()
    env.close()


def test_ctrl_c_during_step_releases_notes_and_closes():
    class Interrupted(DummyAdapter):
        interrupted = False
        closed = False
        panic = []
        def send(self, commands):
            if not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt
            self.panic.extend(commands)
        def close(self):
            self.closed = True
    adapter = Interrupted()
    env = LogicProEnv(adapter, expressive_instrument('agent'))
    env.reset()
    with pytest.raises(KeyboardInterrupt):
        env.step(env.action_space.sample())
    assert adapter.closed
    assert any(c.kind == 'midi.all_sound_off' for c in adapter.panic)
    env.close()


def test_ctrl_c_during_partial_connect_closes_backend():
    class Interrupted(DummyAdapter):
        closed = False
        def connect(self):
            raise KeyboardInterrupt
        def close(self):
            self.closed = True
    adapter = Interrupted()
    env = LogicProEnv(adapter, expressive_instrument('agent'))
    with pytest.raises(KeyboardInterrupt):
        env.reset()
    assert adapter.closed
    assert not env._connected and not env._connecting


def test_repeated_ctrl_c_does_not_abort_cleanup_and_handler_is_restored():
    import signal
    previous = signal.getsignal(signal.SIGINT)
    class RepeatedInterrupt(DummyAdapter):
        closed = False
        def close(self):
            assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
            signal.raise_signal(signal.SIGINT)
            self.closed = True
    adapter = RepeatedInterrupt()
    env = LogicProEnv(adapter, expressive_instrument('agent'))
    env.reset()
    env.close()
    assert adapter.closed
    assert signal.getsignal(signal.SIGINT) == previous


def test_cleanup_timeout_restores_interrupt_handler():
    import signal
    release = threading.Event()
    previous = signal.getsignal(signal.SIGINT)
    class Stalled(DummyAdapter):
        def close(self):
            release.wait()
    env = LogicProEnv(Stalled(), expressive_instrument('agent'))
    env.reset()
    try:
        with pytest.raises(TimeoutError):
            env.close(timeout=.01)
        assert signal.getsignal(signal.SIGINT) == previous
    finally:
        release.set()
        env.close()


def test_real_sigint_triggers_full_note_shutdown():
    import signal
    previous = signal.getsignal(signal.SIGINT)
    class Interrupted(DummyAdapter):
        armed = False
        closed = False
        def send(self, commands):
            super().send(commands)
            if self.armed:
                self.armed = False
                signal.raise_signal(signal.SIGINT)
        def close(self):
            self.closed = True
    adapter = Interrupted()
    env = LogicProEnv(adapter, expressive_instrument('agent'))
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        env.reset()
        adapter.armed = True
        with pytest.raises(KeyboardInterrupt):
            env.step(env.action_space.sample())
        assert adapter.closed
        assert {c.values['note'] for c in adapter.commands if c.kind == 'midi.note_off'} == set(range(128))
        assert any(c.kind == 'midi.cc.64' and c.values['value'] == 0 for c in adapter.commands)
        assert any(c.kind == 'midi.all_notes_off' for c in adapter.commands)
        assert any(c.kind == 'midi.all_sound_off' for c in adapter.commands)
        assert signal.getsignal(signal.SIGINT) == signal.default_int_handler
    finally:
        signal.signal(signal.SIGINT, previous)
        env.close()
