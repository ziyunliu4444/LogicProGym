"""Opt-in run manifests; never overwrite an existing experiment."""
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import hashlib
import json
from pathlib import Path
from logicprogym.checkpoints import session_metadata

def write_manifest(output, config_path, *, seed, checkpoint=None, labels=None):
    """Save configuration, versions, seed, and optional checkpoint provenance.

    The checkpoint reference is not loaded as a policy. Labels can identify
    a Logic project or preset manually; no project state or audio is captured.
    """
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
        raise ValueError('seed must be a nonnegative integer or None')
    versions = {}
    for package in ('gymnasium', 'numpy', 'mido', 'python-rtmidi', 'sounddevice', 'torch'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    reference = None
    if checkpoint is not None:
        path = Path(checkpoint)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        reference = {'path': str(path), 'sha256': digest.hexdigest()}
    manifest = {
        'manifest_schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'session': session_metadata(config_path), 'seed': seed,
        'dependencies': versions, 'checkpoint': reference, 'labels': labels or {},
        'limitations': 'Does not capture or restore Logic project state, human performance or audio.',
    }
    # Serialize before touching the output, so invalid metadata leaves no file.
    payload = json.dumps(manifest, indent=2, allow_nan=False) + '\n'
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    return manifest
