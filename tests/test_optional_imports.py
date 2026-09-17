"""Importing the package must not eagerly load device libraries."""

import subprocess
import sys


def test_core_import_defers_device_libraries():
    code = '''
import sys
from importlib.abc import MetaPathFinder
class BlockMidi(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mido', 'sounddevice'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, BlockMidi())
import logicprogym
import logicprogym.cli
assert 'mido' not in sys.modules
assert 'sounddevice' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
