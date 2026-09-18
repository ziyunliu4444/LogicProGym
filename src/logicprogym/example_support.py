"""Shared CLI demonstration helpers, not Gymnasium environment behavior."""

import multiprocessing
import os
import signal
import time
import gymnasium as gym
import numpy as np

def make_action(space, track, note):
    """Build a neutral action for the expressive-instrument configuration."""
    action = {}
    for key, subspace in space.spaces.items():
        if not isinstance(subspace, (gym.spaces.Box, gym.spaces.MultiBinary)):
            raise ValueError(f"Unsupported action {key}: use the expressive_instrument preset")
        value = np.zeros(subspace.shape, dtype=subspace.dtype)
        if key.endswith('/velocity'):
            value.fill(0.5)
        elif key.endswith('/expression'):
            value.fill(0.75)
        if isinstance(subspace, gym.spaces.Box):
            value = np.clip(value, subspace.low, subspace.high)
        action[key] = value
    if note is not None:
        action[f'{track}/note_gate'][note] = 1
    if not space.contains(action):
        raise ValueError('Configuration is incompatible with this example')
    return action


def supervise(worker_target, cleanup_timeout=10.0):
    """CLI-only guard: a separate process can stop even a GIL-held native hang.

    No deadline applies to training itself. Cleanup (or Ctrl-C) starts the
    deadline. Forced termination is reported as failure, never clean shutdown.
    """
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=worker_target, args=(sender,))
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



def run_demo(policy, description, *, on_cleanup=None, on_step=None, allow_read_only=False):
    """Run one deterministic musical policy through the public Gymnasium API.

    The YAML owns hardware routing. CLI options control only run duration/rate.
    Validate the policy output before connecting so schema mistakes send nothing.
    """
    import argparse
    import math
    import logicprogym

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('config', help='Configured session YAML')
    parser.add_argument('--steps', type=int, default=120, help='0 runs until Ctrl-C')
    parser.add_argument('--control-hz', type=float, default=2.0)
    if allow_read_only:
        parser.add_argument('--read-only', action='store_true',
                            help='Send zero parameter movements; monitor manual knob changes')
    args = parser.parse_args()
    if args.steps < 0:
        parser.error('--steps must be nonnegative')
    if not math.isfinite(args.control_hz) or not 0 < args.control_hz <= 50:
        parser.error('--control-hz must be finite, greater than 0 and at most 50')
    options = {} if args.steps == 0 else {'max_episode_steps': args.steps}
    env = gym.make(logicprogym.ENV_ID, config_path=args.config, **options)
    try:
        if not env.action_space.contains(policy(0, args.control_hz)):
            raise ValueError('Policy actions do not match the YAML; use this demo’s template')
        env.reset()
        print('Play the human track. Scripted policy running; Ctrl-C stops.', flush=True)
        if getattr(args, 'read_only', False):
            print('Read-only: no parameter movements requested; move knobs in Logic manually.', flush=True)
        step = 0
        while args.steps == 0 or step < args.steps:
            started = time.monotonic()
            action = policy(step, args.control_hz)
            if getattr(args, 'read_only', False):
                action = {key: np.zeros_like(value) for key, value in action.items()}
            if not env.action_space.contains(action):
                raise ValueError('Policy emitted an action outside the declared space')
            _, reward, terminated, truncated, info = env.step(action)
            requests = {}
            for key, value in action.items():
                if key.endswith('/note_gate'):
                    requests[key] = np.flatnonzero(value).tolist()
                elif key.endswith('/parameter_vector'):
                    requests[key] = np.round(value, 3).tolist()
            print(f'step={step+1} requested={requests} reward={reward:+.4f}', flush=True)
            snapshot = info.get('snapshot')
            if snapshot is not None:
                for event in snapshot.events:
                    if str(getattr(event.source, 'value', event.source)) == 'human':
                        print(f'HUMAN {event.kind} {event.values}', flush=True)
            if on_step is not None:
                on_step(info, env)
            step += 1
            if terminated or truncated:
                break
            time.sleep(max(0.0, 1.0/args.control_hz - (time.monotonic()-started)))
    except KeyboardInterrupt:
        print('Stopping demonstration...', flush=True)
    finally:
        print('Releasing agent notes and closing...', flush=True)
        if on_cleanup is not None:
            on_cleanup()
        env.close()
        print('Environment closed.', flush=True)
