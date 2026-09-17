"""Observe local-time frames without sending agent actions."""
import argparse
import gymnasium as gym
import logicprogym

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', help='Observation-only YAML with frames enabled')
    parser.add_argument('--frames', type=int, default=100)
    args = parser.parse_args()
    if args.frames < 1:
        parser.error('--frames must be positive')
    env = gym.make(logicprogym.ENV_ID, config_path=args.config,
                   max_episode_steps=args.frames)
    try:
        if env.unwrapped.action_specs or env.unwrapped.frame_clock is None:
            parser.error('Use an observation-only configuration with frames enabled')
        env.reset()
        for _ in range(args.frames):
            observation, _, terminated, truncated, info = env.step(0)
            print(info['frame'], flush=True)
            if 'audio' in info:
                print('audio:', info['audio'], flush=True)
            if terminated or truncated:
                break
    except KeyboardInterrupt:
        print('Stopping frame observation.', flush=True)
    finally:
        env.close()

if __name__ == '__main__':
    main()
