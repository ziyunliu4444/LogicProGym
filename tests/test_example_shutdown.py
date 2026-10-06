"""Exercise terminal process-group interrupts without opening MIDI ports."""
import os
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.mark.skipif(not hasattr(os, "setpgrp"), reason="POSIX terminal signals")
def test_terminal_ctrl_c_does_not_interrupt_cleanup(tmp_path):
    script = tmp_path / 'shutdown_probe.py'
    script.write_text('''
import os, signal, threading, time
from examples._cli_shutdown import supervise

def worker(connection):
    def interrupt_terminal():
        time.sleep(.2)
        os.killpg(os.getpgid(os.getppid()), signal.SIGINT)
    threading.Thread(target=interrupt_terminal, daemon=True).start()
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        connection.send('cleanup')
        time.sleep(.3)
        print('NOTES_RELEASED', flush=True)

if __name__ == '__main__':
    raise SystemExit(supervise(worker, cleanup_timeout=2))
''')
    result = subprocess.run([sys.executable, str(script)], start_new_session=True,
                            capture_output=True, text=True, timeout=10,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'NOTES_RELEASED' in result.stdout
    assert 'KeyboardInterrupt' not in result.stderr
