"""Live reset check: two note/bend/sustain trials in the same environment.

Use a dedicated agent MIDI route, separate from the human track. Configure
agent-owned pitch_bend and sustain resets to zero in the supplied YAML.
This checks audible behavior manually, not Logic acknowledgments.
"""

import argparse
import time

import gymnasium as gym
import yaml
import logicprogym

from logicprogym.example_support import make_action, supervise


def main(on_cleanup=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config')
    parser.add_argument('--track', default='agent')
    parser.add_argument('--seconds', type=float, default=4.0,
                        help='Seconds to listen before and after each reset')
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('--seconds must be between 0 and 60')
    # Validate the opt-in before opening ports or playing a sustained note.
    with open(args.config) as source:
        config = yaml.safe_load(source)
    resets = config.get('environment', {}).get('reset_controls', {})
    controls = {item['action']: item for item in resets.get('controls', [])}
    for name in ('pitch_bend', 'sustain'):
        item = controls.get(f'{args.track}/{name}', {})
        if (resets.get('enabled') is not True or item.get('ownership') != 'agent'
                or item.get('value') != [0.0]):
            parser.error(f'Configure an agent-owned {args.track}/{name} reset with value: [0.0]')

    env = gym.make(logicprogym.ENV_ID, config_path=args.config)
    try:
        # This test must not send neutral actions to other controlled tracks.
        if any(not key.startswith(args.track + '/') for key in env.action_space.spaces):
            raise ValueError('Use a session with only one agent-controlled track')
        action = make_action(env.action_space, args.track, 60)
        action[f'{args.track}/pitch_bend'][:] = .5
        action[f'{args.track}/sustain'][:] = 1.0
        if not env.action_space.contains(action):
            raise ValueError('This test requires the expressive_instrument action preset')
        env.reset()
        print('Keep playing the human track; it should remain unaffected.', flush=True)
        for episode in range(1, 3):
            env.step(action)
            print(f'Trial {episode}: note 60 held, bend=+0.5, sustain=1.', flush=True)
            time.sleep(args.seconds)
            _, info = env.reset()
            print(f'Trial {episode} RESET: {info.get("reset_controls")}', flush=True)
            print('Listen: agent should stop (allow release tail). Bend and sustain '
                  'were requested at zero; human track should still play.', flush=True)
            time.sleep(args.seconds)
        print('Two reset trials completed in one environment. '
              'Confirm the audible result; this is not an automatic live PASS.', flush=True)
    except KeyboardInterrupt:
        print('Stopping reset test...', flush=True)
    finally:
        print('Releasing agent notes and closing...', flush=True)
        if on_cleanup is not None:
            on_cleanup()
        env.close()
        print('Environment closed.', flush=True)


def _reset_worker(connection):
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(supervise(worker_target=_reset_worker))
