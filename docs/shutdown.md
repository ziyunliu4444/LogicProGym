# Public environment shutdown

The training and reset-test CLIs use a supervised worker. Training saves before
MIDI cleanup. After ten seconds of stuck cleanup, the supervisor kills its
worker with a warning and exit code 124. This does not guarantee note release
in Logic; stop residual sound there if necessary. A printed `Saved` message
confirms persistence, not cleanup. The reusable environment never forcibly
exits its caller.

`env.close()` attempts sustain release, note-off, all-notes-off and all-sound-off
for configured note tracks, then closes the backend. It waits up to three
seconds by default. It never calls `os._exit()`.

Always use `try/finally` around a live session:

```python
env = logicprogym.make("configs/my_session.yaml")
try:
    observation, info = env.reset()
    # Run your policy here.
finally:
    env.close()
```

A `TimeoutError` means native cleanup is still pending, not that ports have
been released. The environment blocks reset while that cleanup runs; calling
close again waits for the same worker. A cleanup exception is reported as a
`RuntimeError`. This does not guarantee recovery from native calls that hold
Python's interpreter lock, nor cleanup after SIGKILL. Hardware verification is
still required. Older live examples retain their explicit process-exit
workarounds.

To exercise the public API against configured tracks:

```bash
python live_tests/logic_public_api.py configs/my_session.yaml --steps 20
```

This hardware smoke test samples controls on all configured agent tracks and
limits note gates to middle C on each note track. Its reward is the base
environment's zero reward; it is not a training algorithm. Verify routing,
episode completion, silence after close, and subsequent reopening in Logic.
