"""Process guard for live example CLIs; contains no environment or policy logic."""

import multiprocessing
import os
import signal
import time

def _isolated_worker(worker_target, sender):
    # Terminal Ctrl-C belongs to the supervisor. It forwards one interrupt;
    # receiving both the terminal signal and the forwarded signal can abort
    # the worker's finally block while it is releasing MIDI notes.
    if hasattr(os, 'setpgrp'):
        os.setpgrp()
    worker_target(sender)


def supervise(worker_target, cleanup_timeout=10.0):
    """CLI-only guard: a separate process can stop even a GIL-held native hang.

    No deadline applies to training itself. Cleanup (or Ctrl-C) starts the
    deadline. Forced termination is reported as failure, never clean shutdown.
    """
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=_isolated_worker, args=(worker_target, sender))
    worker.start()
    sender.close()
    deadline = None
    try:
        while worker.is_alive():
            try:
                if receiver.poll(.1):
                    try:
                        phase = receiver.recv()
                    except EOFError:
                        phase = None
                    if phase == 'cleanup' and deadline is None:
                        deadline = time.monotonic() + cleanup_timeout
                worker.join(.05)
            except KeyboardInterrupt:
                # Give the worker time to save and release notes before killing.
                if deadline is None:
                    deadline = time.monotonic() + cleanup_timeout
                    if worker.is_alive():
                        os.kill(worker.pid, signal.SIGINT)
            if deadline is not None and time.monotonic() >= deadline and worker.is_alive():
                print('WARNING: MIDI shutdown stalled; stopping the worker. '
                      'Note release is not confirmed. If sound remains, stop it in Logic. '
                      'Only a printed Saved message confirms checkpoint saving.', flush=True)
                worker.kill()
                worker.join()
                return 124
        worker.join()
        return worker.exitcode
    finally:
        receiver.close()

