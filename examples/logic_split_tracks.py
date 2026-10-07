"""Human plays one track while a scripted agent plays notes and moves knobs on another.

This is a deterministic
arpeggio/parameter-motion demonstration, not a learned accompaniment policy.
Use separate human/agent MIDI routes and verify the two mapped parameters.
"""
import math
import time
import numpy as np
import argparse
import gymnasium as gym
import logicprogym

NOTES = (48, 52, 55, 60)


def agent_action(step: int, control_hz: float) -> dict[str, np.ndarray]:
    """Create one held agent note plus two gentle parameter velocities."""

    note = NOTES[(step // max(1, round(control_hz))) % len(NOTES)]
    gates = np.zeros(128, dtype=np.int8)
    gates[note] = 1
    phase = 2.0 * math.pi * step / (control_hz * 8.0)
    return {
        "agent/note_gate": gates,
        "agent/velocity": np.full(128, 0.60, dtype=np.float32),
        "agent/pitch_bend": np.asarray([0.0], dtype=np.float32),
        "agent/expression": np.asarray([0.75], dtype=np.float32),
        "agent/sustain": np.asarray([0.0], dtype=np.float32),
        "agent/parameter_vector": np.asarray(
            [0.20 * math.sin(phase), -0.20 * math.sin(phase)], dtype=np.float32
        ),
    }



def main(on_cleanup=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', help='Configured session YAML')
    parser.add_argument('--steps', type=int, default=120, help='0 runs until Ctrl-C')
    parser.add_argument('--control-hz', type=float, default=2.0)
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
        step = 0
        while args.steps == 0 or step < args.steps:
            started = time.monotonic()
            action = agent_action(step, args.control_hz)
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
