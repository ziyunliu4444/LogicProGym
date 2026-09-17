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
