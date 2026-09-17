"""A Gymnasium agent hears raw Logic audio and adjusts a learned MIDI CC knob.

This deterministic example maps waveform energy to CC level. It demonstrates
an audio-conditioned policy, not training, and generates no musical notes.
"""

import argparse
from pathlib import Path
import sys
import time

import gymnasium as gym
import numpy as np

import logicprogym
from logicprogym.config import LogicProGymConfig


class AudioEnergyPolicy:
    """Compute RMS from raw valid stereo frames; hold the last request if stale."""

    def __init__(self, quiet_db=-60., loud_db=-12.):
        if not np.isfinite([quiet_db, loud_db]).all() or quiet_db >= loud_db:
            raise ValueError('quiet_db must be less than loud_db, both finite')
        self.quiet_db, self.loud_db = quiet_db, loud_db
        self.level = .5
        self.sequence = None

    def act(self, observation, info):
        waveform = observation['audio']
        mask = observation['audio_valid']
        sequence = info.get('audio', {}).get('sequence')
        details = dict(status='waiting/holding', db=None)
        # A full fresh window avoids treating reset padding or repeated audio as
        # a new musical observation. Initial request is the neutral midpoint.
        if np.all(mask) and sequence is not None and sequence != self.sequence:
            self.sequence = sequence
            rms = float(np.sqrt(np.mean(np.square(waveform, dtype=np.float64))))
            db = 20 * np.log10(max(rms, 1e-6))
            energy = float(np.clip((db - self.quiet_db) / (self.loud_db - self.quiet_db), 0, 1))
            target = .15 + .70 * energy
            self.level += .2 * (target - self.level)
            details = dict(status='listening', db=db)
        return np.array([self.level], dtype=np.float32), details


def default_config():
    """Find the shipped example in either a source checkout or installed wheel."""
    source = Path(__file__).resolve().parents[1] / 'configs/examples/logic_audio_agent.yaml'
    return source if source.is_file() else Path(sys.prefix) / 'share/logicprogym/configs/logic_audio_agent.yaml'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=default_config())
    parser.add_argument('--steps', type=int, default=300, help='Control steps; 0 runs until Ctrl-C')
    parser.add_argument('--interval', type=float, default=.1, help='Seconds between control steps')
    parser.add_argument('--quiet-db', type=float, default=-60)
    parser.add_argument('--loud-db', type=float, default=-12)
    args = parser.parse_args()
    if args.steps < 0 or not np.isfinite(args.interval) or args.interval <= 0:
        parser.error('--steps must be nonnegative and --interval must be finite and positive')
    policy = AudioEnergyPolicy(args.quiet_db, args.loud_db)
    config = LogicProGymConfig.from_yaml(args.config)
    if len(config.actions) != 1 or not config.actions[0].target.startswith('midi.cc.'):
        parser.error('This example requires exactly one mapped MIDI CC action')
    action_key = config.actions[0].id
    cc = int(config.actions[0].target.rsplit('.', 1)[1])
    env = gym.make(logicprogym.ENV_ID, config_path=args.config,
                   **({'max_episode_steps': args.steps} if args.steps else {}))
    env = gym.wrappers.RecordEpisodeStatistics(env)
    try:
        space = env.action_space[action_key]
        if (not isinstance(space, gym.spaces.Box) or space.shape != (1,) or
                not space.contains(np.array([.15], dtype=np.float32)) or
                not space.contains(np.array([.85], dtype=np.float32))):
            raise ValueError('Use a continuous CC action with shape [1] and range [0, 1]')
        if 'audio' not in env.observation_space.spaces:
            raise ValueError('Enable environment.audio in this configuration')
        observation, info = env.reset()
        print(f'Play notes in Logic. Audio energy controls {action_key} via CC{cc}.', flush=True)
        print('Keep Logic Learn Mode OFF. Initial CC request is 50%; Ctrl-C stops.', flush=True)
        step = 0
        while True:
            started = time.monotonic()
            value, details = policy.act(observation, info)
            age = info.get('audio', {}).get('age_seconds')
            observation, reward, terminated, truncated, info = env.step({action_key: value})
            step += 1
            db = 'unavailable' if details['db'] is None else f"{details['db']:.1f} dBFS"
            wire_value = int(round(float(value[0]) * 127))
            print(f"step={step} audio={db} status={details['status']} age={age} "
                  f"requested CC{cc}={wire_value} reward={reward:.1f}", flush=True)
            if terminated or truncated:
                print(f"Episode: {info.get('episode')}", flush=True)
                break
            time.sleep(max(0., args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print('\nStopping audio agent...', flush=True)
    finally:
        env.close()
        print('Environment closed.', flush=True)


if __name__ == '__main__':
    main()
