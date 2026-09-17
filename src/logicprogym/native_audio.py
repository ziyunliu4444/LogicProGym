"""Driver-free application audio input using a bundled macOS Core Audio helper."""

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import tempfile
from threading import Event, Thread

import numpy as np

from logicprogym.audio import AudioInput


def require_macos():
    """Fail before attempting a compiler or opening capture on unsupported hosts."""
    if platform.system() != 'Darwin':
        raise RuntimeError('Native process audio capture requires macOS 14.2 or later')
    parts = tuple(int(part) for part in platform.mac_ver()[0].split('.')[:2])
    if parts < (14, 2):
        raise RuntimeError('Native process audio capture requires macOS 14.2 or later')


def build_helper(build_dir=None):
    """Compile once per source/architecture version; no downloads or driver installs.

    The app bundle and embedded usage description let macOS identify the audio
    permission request. A local ad-hoc signature is used for development builds.
    """
    require_macos()
    source = Path(__file__).with_name('native') / 'LogicAudioTap.swift'
    plist = source.with_name('Info.plist')
    digest = hashlib.sha256(source.read_bytes() + plist.read_bytes() +
                            platform.machine().encode()).hexdigest()[:16]
    root = Path(build_dir).resolve() if build_dir else Path.home() / 'Library/Caches/logicprogym/native-audio'
    destination = root / digest / 'LogicProGym Audio.app'
    binary = destination / 'Contents/MacOS/logicprogym-audio-tap'
    if binary.is_file():
        return binary
    root.mkdir(parents=True, exist_ok=True)
    # Build separately so interruption cannot leave a cached partial executable.
    with tempfile.TemporaryDirectory(prefix='build-', dir=root) as temporary:
        stage = Path(temporary) / 'LogicProGym Audio.app'
        contents = stage / 'Contents'
        (contents / 'MacOS').mkdir(parents=True)
        shutil.copyfile(plist, contents / 'Info.plist')
        executable = contents / 'MacOS/logicprogym-audio-tap'
        command = ['xcrun', 'swiftc', '-swift-version', '5', '-O', '-framework', 'CoreAudio',
                   '-framework', 'AudioToolbox', '-framework', 'AppKit',
                   '-module-cache-path', str(root / 'module-cache'),
                   '-Xlinker', '-sectcreate', '-Xlinker', '__TEXT', '-Xlinker', '__info_plist',
                   '-Xlinker', str(plist), str(source), '-o', str(executable)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
            subprocess.run(['codesign', '--force', '--sign', '-', str(stage)],
                           check=True, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as error:
            details = getattr(error, 'stderr', '') or str(error)
            raise RuntimeError('Could not build native audio helper. Install Apple Xcode Command Line '
                               f'Tools (xcode-select --install), then retry.\n{details}') from error
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            stage.rename(destination)
    return binary


def decode_packet(packet):
    """Decode bounded stereo PCM packets; reject corrupt sizes and protocol data."""
    if len(packet) != 512:
        raise ValueError('Truncated native audio packet')
    magic, sequence, frames, flags = struct.unpack_from('<4sIII', packet)
    if magic != b'DGA1' or not 1 <= frames <= 62 or flags != 0:
        raise ValueError('Invalid native audio packet')
    samples = np.frombuffer(packet, dtype='<f4', count=frames * 2, offset=16).reshape(frames, 2)
    return sequence, samples


def resolve_logic_application(applications):
    """Select only a known Logic edition; never fall back to another audio app."""
    logic_ids = {'com.apple.logic10', 'com.apple.mobilelogic'}
    candidates = [app for app in applications if app.get('bundle_id') in logic_ids]
    if not candidates:
        raise RuntimeError('No running Logic Pro or Logic Pro Creator Studio was found. '
                           'Open Logic, then retry. Use --source native --list to inspect running apps.')
    if len(candidates) != 1:
        choices = ', '.join(app['bundle_id'] for app in candidates)
        raise RuntimeError(f'Multiple Logic applications are running ({choices}). '
                           'Choose one explicitly with --bundle-id or close the other instance.')
    return candidates[0]['bundle_id']


class NativeAudioInput(AudioInput):
    """Capture one application; auto-detect its rate while keeping fixed window shape."""

    def __init__(self, bundle_id='auto', window_frames=4800, channels=2,
                 sample_rate=None, helper_path=None, build_dir=None):
        if channels != 2:
            raise ValueError('Native application capture currently supports stereo (channels: 2)')
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError('bundle_id must be a nonempty application identifier')
        super().__init__(f'application:{bundle_id}', sample_rate=sample_rate or 48000,
                         channels=channels, window_frames=window_frames)
        if sample_rate is not None and (not isinstance(sample_rate, int) or sample_rate <= 0):
            raise ValueError('sample_rate must be a positive integer or omitted for automatic detection')
        self.expected_rate = sample_rate
        self.bundle_id = bundle_id
        self.resolved_bundle_id = None if bundle_id == 'auto' else bundle_id
        self.helper_path = helper_path
        self.build_dir = build_dir
        self.process = None
        self.reader = self.errors_reader = None
        self.ready = Event()
        self.stopping = Event()
        self.failure = None
        self.errors = deque(maxlen=8)

    def _read_errors(self, pipe):
        # Bound retained diagnostics; always drain stderr to avoid pipe backpressure.
        for line in iter(lambda: pipe.readline(4096), b''):
            self.errors.append(line.decode('utf8', errors='replace').strip())

    def _read_audio(self, pipe):
        try:
            line = pipe.readline(4096)
            if not line:
                raise RuntimeError('Native audio helper exited before sending its format')
            header = json.loads(line)
            rate = header.get('sample_rate')
            if (header.get('protocol') != 1 or header.get('channels') != 2 or
                    header.get('bundle_id') != self.resolved_bundle_id or
                    not isinstance(rate, (int, float)) or not np.isfinite(rate) or rate <= 0):
                raise ValueError('Invalid native audio format header')
            if self.expected_rate is not None and rate != self.expected_rate:
                raise ValueError(f'Logic audio rate is {rate:g} Hz, configured {self.expected_rate}. '
                                 'Match the rate or omit sample_rate for automatic detection.')
            self.sample_rate = rate
            self.ready.set()
            previous = None
            while not self.stopping.is_set():
                packet = pipe.read(512)
                if not packet:
                    if not self.stopping.is_set():
                        raise RuntimeError('Native audio helper stopped')
                    break
                sequence, samples = decode_packet(packet)
                gap = previous is not None and sequence != (previous + 1) % (2 ** 32)
                self._capture(samples, len(samples), None, gap)
                previous = sequence
        except Exception as error:
            if not self.stopping.is_set():
                self.failure = str(error)
                self.ready.set()

    def _failure_message(self):
        # Lookup and format failures occur independently of audio permission.
        # Keep the helper's specific diagnostic instead of suggesting permission
        # changes for every failure.
        return f'{self.failure or "Native audio helper exited"}. ' + '\n'.join(tuple(self.errors))

    def start(self):
        if self.process is not None:
            if self.failure or self.process.poll() is not None:
                raise RuntimeError(self._failure_message())
            return
        require_macos()
        helper = Path(self.helper_path) if self.helper_path else build_helper(self.build_dir)
        if self.bundle_id == 'auto':
            listed = subprocess.run([str(helper), '--list'], capture_output=True,
                                    text=True, check=True, timeout=10)
            self.resolved_bundle_id = resolve_logic_application(json.loads(listed.stdout))
        else:
            self.resolved_bundle_id = self.bundle_id
        self.device = f'application:{self.resolved_bundle_id}'
        self.clear()
        self.ready.clear()
        self.stopping.clear()
        self.errors.clear()
        self.failure = None
        try:
            self.process = subprocess.Popen([str(helper), '--bundle-id', self.resolved_bundle_id],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True)
            self.errors_reader = Thread(target=self._read_errors, args=(self.process.stderr,), daemon=True)
            self.reader = Thread(target=self._read_audio, args=(self.process.stdout,), daemon=True)
            self.errors_reader.start()
            self.reader.start()
            if not self.ready.wait(30):
                raise TimeoutError('Native audio startup timed out. Check macOS audio recording permission.')
            if self.failure:
                self.errors_reader.join(.1)
                raise RuntimeError(self._failure_message())
        except BaseException:
            self.close()
            raise

    def read(self):
        if self.failure or (self.process is not None and self.process.poll() is not None):
            raise RuntimeError(self._failure_message())
        audio, valid, info = super().read()
        return audio, valid, {**info, 'source': 'native', 'bundle_id': self.resolved_bundle_id}

    def close(self):
        self.stopping.set()
        process = self.process
        if process is None:
            return
        # Closing stdin asks Swift to stop Core Audio and destroy its private device.
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        for thread in (self.reader, self.errors_reader):
            if thread is not None:
                thread.join(timeout=1)
        process.stdout.close()
        process.stderr.close()
        self.process = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--list', action='store_true', help='List running applications without capturing')
    args = parser.parse_args()
    try:
        helper = build_helper(args.build_dir)
        if args.list:
            subprocess.run([str(helper), '--list'], check=True, timeout=10)
        else:
            print(helper)
    except (RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
