"""Verify an installed wheel from outside the source checkout, without MIDI IO.

Run using the Python interpreter of a fresh environment with logicprogym
installed. For example: /tmp/release-venv/bin/python tools/release_smoke.py
"""

from importlib.metadata import version
from pathlib import Path
import subprocess
import sys

import gymnasium as gym
import logicprogym


def installed_templates(base):
    """Check both packaged template locations and include future additions."""
    canonical = base / 'configs/examples'
    paths = sorted(canonical.glob('*.yaml'))
    names = {path.name for path in paths}
    required = {'logic_discovery.yaml', 'logic_frames.yaml'}
    assert required <= names, f'Missing required templates: {required - names}'
    legacy = base / 'configs'
    legacy_names = {path.name for path in legacy.glob('*.yaml')}
    assert names == legacy_names, 'Packaged template locations disagree'
    for path in paths:
        assert path.read_bytes() == (legacy / path.name).read_bytes(), path.name
    return paths


def main():
    base = Path(sys.prefix) / 'share/logicprogym'
    templates = installed_templates(base)
    for path in templates:
        filename = path.name
        env = gym.make(logicprogym.ENV_ID, config_path=path)
        try:
            if isinstance(env.action_space, gym.spaces.Discrete):
                assert env.action_space.n == 1 and env.action_space.contains(0)
            else:
                assert len(env.action_space.spaces) > 0
            if filename == 'logic_audio_agent.yaml':
                assert env.observation_space['audio'].shape == (4800, 2)
        finally:
            env.close()  # No reset: no hardware ports are opened.
        result = subprocess.run([sys.executable, '-m', 'logicprogym.cli', 'preview', str(path)],
                                capture_output=True, text=True, timeout=10, check=True)
        assert 'Control preview' in result.stdout
    for command in ('inspect', 'scan'):
        subprocess.run([sys.executable, '-m', 'logicprogym.cli', 'logic', command, '--help'],
                       capture_output=True, text=True, timeout=10, check=True)
    # Test every shipped runnable entrypoint, including tools and live checks.
    for folder in ('examples', 'tools', 'live_tests'):
        scripts = sorted((base / folder).glob('*.py'))
        assert scripts, folder
        for script in scripts:
            subprocess.run([sys.executable, str(script), '--help'], capture_output=True,
                           timeout=15, check=True)
    assert (base / 'docs/release-status.md').is_file()
    native_sources = Path(logicprogym.__file__).parent / 'native'
    assert (native_sources / 'LogicAudioTap.swift').is_file()
    assert (native_sources / 'Info.plist').is_file()
    print(f"Installed LogicProGym {version('LogicProGym')}: {len(templates)} templates, CLI and packaged docs passed")


if __name__ == '__main__':
    main()
