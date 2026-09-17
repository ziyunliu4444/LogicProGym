"""Subprocess fixture for the native transport; never opens an audio device."""

import json
import struct
import sys

if '--fail' in sys.argv:
    print('Audio recording permission denied (fixture)', file=sys.stderr)
    sys.exit(1)
header = dict(protocol=1, sample_rate=44100, channels=2, bundle_id='com.apple.logic10')
sys.stdout.buffer.write(json.dumps(header).encode() + b'\n')
for sequence in (0, 2):
    packet = struct.pack('<4sIII', b'DGA1', sequence, 2, 0)
    packet += struct.pack('<4f', .1, .2, .3, .4)
    sys.stdout.buffer.write(packet.ljust(512, b'\0'))
sys.stdout.buffer.flush()
# The parent must release stdin; no arbitrary sleeps in the fixture process.
sys.stdin.buffer.read()
