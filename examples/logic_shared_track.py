"""Human plays notes while a scripted agent moves shared-instrument parameters.

No agent notes are sent.
This is a deterministic musical demonstration, not a trained policy. Verify all
eight mapped parameters first: some instruments have sound-generating controls.
"""
import math
import re
import time
from dataclasses import replace
import numpy as np
import argparse
import gymnasium as gym
import logicprogym
try:  # Support both module imports and direct script execution.
    from ._cli_shutdown import supervise
except ImportError:
    from _cli_shutdown import supervise


def agent_action(step: int, control_hz: float) -> dict[str, np.ndarray]:
    """Phase-shifted relative movements for eight user-selected parameters."""
    phase = 2.0 * math.pi * step / (control_hz * 8.0)
    intensity = 0.35
    return {"shared/parameter_vector": np.asarray([
        intensity * math.sin(phase), intensity * math.cos(phase),
        0.50 * intensity * math.sin(0.5 * phase),
        -0.80 * intensity * math.cos(0.7 * phase),
        0.60 * intensity * math.sin(1.3 * phase),
        -intensity * math.sin(phase),
        0.70 * intensity * math.cos(1.5 * phase),
        -0.60 * intensity * math.sin(2.0 * phase),
    ], dtype=np.float32)}


def print_parameter_readings(info):
    """Show selected feedback, never infer knob positions from sent actions."""
    snapshot = info.get('snapshot')
    diagnostics = {} if snapshot is None else snapshot.diagnostics
    readings = diagnostics.get('mackie', diagnostics).get('parameter_readings', {})
    if not readings:
        print('KNOBS no selected readings; enable plugin_parameters in shared.observe.', flush=True)
        return
    for parameter_id, reading in readings.items():
        name = reading.get('name', parameter_id)
        raw = reading.get('raw')
        age = reading.get('age_seconds')
        age_text = '' if age is None else f' age={age:.2f}s'
        if reading.get('valid') and raw is not None:
            status = f"reported={raw!r} valid=True{age_text}"
        elif reading.get('display_raw') is not None:
            status = (f"displayed={reading['display_raw']!r} "
                      'unverified track/page; cached LCD, freshness unknown')
        elif raw is not None:
            status = f"unavailable last_reported={raw!r} valid=False{age_text}"
        else:
            status = 'waiting for matched numeric feedback'
        print(f'KNOB {name} [{parameter_id}] {status}', flush=True)


def main(on_cleanup=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', help='Configured session YAML')
    parser.add_argument('--steps', type=int, default=120, help='0 runs until Ctrl-C')
    parser.add_argument('--control-hz', type=float, default=2.0)
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
        if not env.action_space.contains(agent_action(0, args.control_hz)):
            raise ValueError('Policy actions do not match the YAML; use this demo’s template')
        observation, info = env.reset()
        print('Play the human track. Scripted policy running; Ctrl-C stops.', flush=True)
        if getattr(args, 'read_only', False):
            print('Read-only: no parameter movements requested; move knobs in Logic manually.', flush=True)
        step = 0
        while args.steps == 0 or step < args.steps:
            started = time.monotonic()
            action = agent_action(step, args.control_hz)
            if getattr(args, 'read_only', False):
                action = {key: np.zeros_like(value) for key, value in action.items()}
            if not env.action_space.contains(action):
                raise ValueError('Policy emitted an action outside the declared space')
            observation, reward, terminated, truncated, info = env.step(action)
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
            print_after_feedback(info, env)
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

def print_after_feedback(info, env, *, feedback_seconds=0.3):
    """Collect asynchronous feedback after movement, before the next action.

    Read only the Mackie cache: never drain human MIDI, send probe movements,
    or create extra Gymnasium steps. Keep the existing observation selection
    and identity/age checks. This monitor does not alter the step's reward.
    """
    base = env.unwrapped
    mackie = getattr(base.adapter, 'mackie', None)
    if mackie is None:
        print_parameter_readings(info)
        return
    snapshot = info.get('snapshot')
    if snapshot is None:
        return
    # A batch can briefly expose several different parameter readings. Preserve
    # each accepted report from this window rather than only its final LCD state.
    reports = dict(snapshot.diagnostics.get('mackie', {}).get('parameter_readings', {}))
    deadline = time.monotonic() + feedback_seconds
    while True:
        selected = base._select_snapshot(mackie.receive())
        for key, reading in selected.diagnostics.get('parameter_readings', {}).items():
            previous = reports.get(key, {})
            if not reading.get('valid') and previous.get('raw') is not None:
                # Keep a historical report visible, but never keep its validity
                # after the decoder invalidates the current display context.
                reports[key] = dict(previous, valid=False)
            else:
                reports[key] = reading
        collect_display_text(mackie, reports)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.02, remaining))
    # Reports describe the time they arrived, not a guarantee that all knobs
    # remain at these values or that every movement generated feedback.
    now = time.monotonic()
    reports = {key: dict(reading, age_seconds=max(0., now-reading['received_at']))
               if reading.get('received_at') is not None else reading
               for key, reading in reports.items()}
    print_parameter_readings({'snapshot': replace(snapshot, diagnostics={
        'mackie': {'parameter_readings': reports}})})


def collect_display_text(mackie, reports):
    """Add terminal-only LCD text without promoting it to an observation.

    Logic may show a value without refreshing the identity header required by
    the verified reader. Only inspect selected bindings with a matching name;
    never derive a percentage from an action or an encoder-ring position.
    """
    service = getattr(mackie, 'service', None)
    bridge = getattr(service, 'bridge', None)
    if bridge is None:
        return
    for binding in mackie.feedback_bindings:
        reading = reports.get(binding['id'])
        if reading is None or reading.get('valid'):
            continue
        controller = bridge.pool.controllers[binding['controller'] - 1]
        name, raw = controller.lcd.strips[binding['slot'] - 1]
        if (name.casefold() == binding['name'].casefold()
                and re.fullmatch(r'[+-]?\d+(?:\.\d+)?\s*%?', raw.strip())):
            reports[binding['id']] = dict(reading, display_raw=raw)


def _worker(connection):
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(supervise(_worker))
