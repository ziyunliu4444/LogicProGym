"""Portable session provenance for example checkpoints (not Logic project state)."""

from importlib.metadata import version
from pathlib import Path
import platform

import yaml


def session_metadata(path):
    """Store the parsed configuration so moving the file does not break resume."""
    package_version = version('LogicProGym')
    return {
        'schema': 1,
        'config': yaml.safe_load(Path(path).read_text()),
        'logicprogym_version': package_version,
        'python': platform.python_version(),
        'platform': platform.platform(),
    }


def validate_session(saved, current):
    """Reject changed routes/actions before opening ports; never guess compatibility."""
    previous = saved.get('session')
    if not previous or previous.get('schema') != current['schema']:
        raise ValueError('Checkpoint has no compatible session metadata; start a new checkpoint')
    if previous['config'] != current['config']:
        raise ValueError('Checkpoint session configuration differs; restore its YAML or start a new checkpoint')
