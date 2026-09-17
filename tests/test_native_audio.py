"""Exercise native IPC, failure propagation and cleanup without system capture."""

import json
from pathlib import Path
import struct
import subprocess
import sys
from threading import Event

import numpy as np
import pytest

from logicprogym import native_audio


def test_packet_validation():
    packet = struct.pack('<4sIII', b'DGA1', 7, 1, 0)
    packet += struct.pack('<2f', .25, -.5)
    packet = packet.ljust(512, b'\0')
    sequence, data = native_audio.decode_packet(packet)
    assert sequence == 7
    np.testing.assert_array_equal(data, [[.25, -.5]])
    for broken in (packet[:-1], b'bad!' + packet[4:], packet[:8] + struct.pack('<I', 63) + packet[12:]):
        with pytest.raises(ValueError):
            native_audio.decode_packet(broken)


def fake_helper(monkeypatch, fail=False):
    fixture = Path(__file__).parent / 'fixtures/native_audio_helper.py'
    real_popen = subprocess.Popen
    launched = []

    def launch(args, **kwargs):
        process = real_popen([sys.executable, str(fixture)] + (['--fail'] if fail else []), **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr(native_audio, 'require_macos', lambda: None)
    monkeypatch.setattr(native_audio.subprocess, 'Popen', launch)
    return launched


def test_native_rate_gap_and_repeated_close(monkeypatch):
    launched = fake_helper(monkeypatch)
    capture = native_audio.NativeAudioInput(bundle_id='com.apple.logic10', helper_path='fixture', window_frames=4)
    for _ in range(2):
        received = Event()
        original = capture._capture

        def consume(*args):
            original(*args)
            if args[-1]:
                received.set()

        with monkeypatch.context() as context:
            context.setattr(capture, '_capture', consume)
            try:
                capture.start()
                assert received.wait(3)
                audio, valid, info = capture.read()
                assert capture.sample_rate == 44100
                assert info['callback_status_count'] == 1
                np.testing.assert_array_equal(valid, [0, 0, 1, 1])
                np.testing.assert_allclose(audio[-2:], [[.1, .2], [.3, .4]])
            finally:
                capture.close()
                capture.close()
        assert launched[-1].poll() is not None
        assert not capture.reader.is_alive()


def test_native_rate_mismatch_closes_helper(monkeypatch):
    launched = fake_helper(monkeypatch)
    capture = native_audio.NativeAudioInput(bundle_id='com.apple.logic10', helper_path='fixture', sample_rate=48000)
    with pytest.raises(RuntimeError, match='44100'):
        capture.start()
    assert capture.process is None and launched[0].poll() is not None


def test_native_startup_failure_is_reported(monkeypatch):
    launched = fake_helper(monkeypatch, fail=True)
    capture = native_audio.NativeAudioInput(bundle_id='com.apple.logic10', helper_path='fixture')
    with pytest.raises(RuntimeError, match='permission denied'):
        capture.start()
    assert capture.process is None and launched[0].poll() is not None


def test_yaml_native_audio_constructs_lazily(tmp_path):
    import yaml
    import logicprogym
    config = yaml.safe_load(Path('configs/examples/logic_midi_only.yaml').read_text())
    config.setdefault('environment', {})['audio'] = dict(source='native', window_frames=256)
    path = tmp_path / 'session.yaml'
    path.write_text(yaml.safe_dump(config))
    env = logicprogym.make(path)
    assert env.observation_space['audio'].shape == (256, 2)
    assert isinstance(env.audio_input, native_audio.NativeAudioInput)
    assert env.audio_input.process is None
    env.close()


@pytest.mark.parametrize('identifier', ['com.apple.logic10', 'com.apple.mobilelogic'])
def test_auto_discovery_supports_both_logic_editions(identifier):
    apps = [{'bundle_id': 'com.example.other'}, {'bundle_id': identifier}]
    assert native_audio.resolve_logic_application(apps) == identifier


def test_auto_discovery_rejects_missing_and_ambiguous_logic():
    with pytest.raises(RuntimeError, match='No running Logic'):
        native_audio.resolve_logic_application([{'bundle_id': 'com.example.other'}])
    with pytest.raises(RuntimeError, match='Multiple Logic'):
        native_audio.resolve_logic_application([
            {'bundle_id': 'com.apple.logic10'}, {'bundle_id': 'com.apple.mobilelogic'}])


def test_lookup_failure_does_not_suggest_permission_changes():
    capture = native_audio.NativeAudioInput()
    capture.failure = 'No matching application'
    assert 'permission' not in capture._failure_message().lower()
