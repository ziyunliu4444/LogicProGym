"""Keep installed-package verification complete without opening live devices."""

from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

import pytest


@pytest.fixture
def smoke():
    return runpy.run_path(str(Path(__file__).parents[1] / 'tools/release_smoke.py'))


@pytest.fixture
def installed(tmp_path):
    base = tmp_path / 'share/logicprogym'
    canonical = base / 'configs/examples'
    canonical.mkdir(parents=True)
    for source in (Path(__file__).parents[1] / 'configs/examples').glob('*.yaml'):
        shutil.copyfile(source, canonical / source.name)
        shutil.copyfile(source, base / 'configs' / source.name)
    return base


def test_template_discovery_includes_new_files(smoke, installed):
    for folder in (installed / 'configs', installed / 'configs/examples'):
        (folder / 'future_example.yaml').write_text('tracks: []\n')
    names = {p.name for p in smoke['installed_templates'](installed)}
    assert {'logic_discovery.yaml', 'logic_frames.yaml', 'future_example.yaml'} <= names


def test_template_discovery_rejects_missing_discovery(smoke, installed):
    (installed / 'configs/examples/logic_discovery.yaml').unlink()
    with pytest.raises(AssertionError, match='Missing required templates'):
        smoke['installed_templates'](installed)


def test_template_discovery_rejects_stale_compatibility_copy(smoke, installed):
    (installed / 'configs/logic_discovery.yaml').write_text('stale: true\n')
    with pytest.raises(AssertionError, match='logic_discovery.yaml'):
        smoke['installed_templates'](installed)


def test_smoke_handles_no_action_templates_and_cli_help(smoke, installed, monkeypatch, capsys):
    for folder in ('examples', 'tools', 'live_tests'):
        (installed / folder).mkdir()
        (installed / folder / 'example.py').write_text('')
    (installed / 'docs').mkdir()
    (installed / 'docs/release-status.md').write_text('Support scope')
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout='Control preview')

    # Construct actual template environments, but never reset/connect them.
    monkeypatch.setattr(smoke['subprocess'], 'run', run)
    monkeypatch.setitem(smoke['main'].__globals__, 'sys',
                        SimpleNamespace(prefix=str(installed.parents[1]), executable='python'))
    smoke['main']()
    count = len(list((installed / 'configs/examples').glob('*.yaml')))
    assert f'{count} templates' in capsys.readouterr().out
    assert any('logic_discovery.yaml' in str(call) for call in calls)
    for name in ('inspect', 'scan'):
        assert any(call[-3:] == ['logic', name, '--help'] for call in calls)
