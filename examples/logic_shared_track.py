"""Human plays notes while a scripted agent moves shared-instrument parameters.

No agent notes are sent.
This is a deterministic musical demonstration, not a trained policy. Verify all
eight mapped parameters first: some instruments have sound-generating controls.
"""
import math
import time
import numpy as np
import argparse
import gymnasium as gym
import logicprogym

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
    readings = logicprogym.parameter_readings(info)
    if not readings:
        print('KNOBS no selected readings; enable plugin_parameters in shared.observe.', flush=True)
    for reading in readings.values():
        print(f'KNOB {reading.name} [{reading.id}] raw={reading.raw!r} '
              f'age={reading.age_seconds} value={reading.value} valid={reading.valid}', flush=True)


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
            print_parameter_readings(info)
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

if __name__ == '__main__':
    main()
