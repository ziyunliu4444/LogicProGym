"""Watch a learned CC20 cutoff return to its configured baseline on reset.

No notes, Mackie messages, or Learn commands are sent. The baseline is explicit;
this does not read or remember the knob's pre-test position.
"""
import argparse
import time
import numpy as np
import gymnasium as gym
import logicprogym
from logicprogym.config import LogicProGymConfig

from logicprogym.example_support import supervise


def main(on_cleanup=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config')
    parser.add_argument('--seconds', type=float, default=4)
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('--seconds must be greater than 0 and at most 60')
    config = LogicProGymConfig.from_yaml(args.config)
    if (len(config.actions) != 1 or config.actions[0].id != 'agent/cutoff'
            or config.actions[0].target != 'midi.cc.20'):
        parser.error('Use a session containing only agent/cutoff mapped to midi.cc.20')
    resets = config.environment.get('reset_controls', {})
    if resets.get('enabled') is not True or resets.get('controls') != [
            {'action': 'agent/cutoff', 'ownership': 'agent', 'value': [0.5]}]:
        parser.error('Configure an agent-owned agent/cutoff reset value of [0.5]')
    env = gym.make(logicprogym.ENV_ID, config_path=args.config)
    try:
        print('Learn Mode OFF. Watch the CC20-mapped cutoff. No notes are sent.', flush=True)
        for value in (.85, .15):
            _, info = env.reset()
            print('RESET: requested baseline 50% (CC20 value 64). Check the knob in Logic.', flush=True)
            print(info.get('reset_controls'), flush=True)
            time.sleep(args.seconds)
            env.step({'agent/cutoff': np.array([value], dtype=np.float32)})
            print(f'ACTION: requested cutoff {value:.0%}.', flush=True)
            time.sleep(args.seconds)
        env.reset()
        print('FINAL RESET: requested 50% again. Confirm the knob returned.', flush=True)
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        print('Interrupted; the knob may remain at its last requested position.', flush=True)
    finally:
        print('Closing MIDI...', flush=True)
        if on_cleanup:
            on_cleanup()
        env.close()
        print('Environment closed.', flush=True)


def _worker(connection):
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(supervise(worker_target=_worker))
