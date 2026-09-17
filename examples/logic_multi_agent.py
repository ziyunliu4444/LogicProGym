"""Human Track 1, MIDI/Mackie synth Track 2, MIDI trombone Track 3.

Two deterministic demonstration policies share one Gymnasium action dictionary.
No articulation CC is sent. Ctrl-C closes the environment.
"""

import argparse
import math
from pathlib import Path
import time
import sys

import gymnasium as gym
import numpy as np
import logicprogym


def action_at(step):
    """Separate note edges with rests and smoothly vary the trombone bend."""
    gates = np.zeros(128, dtype=np.int8)
    note = (48, 52, 55, 52)[(step // 12) % 4]
    if step % 12 < 10:
        gates[note] = 1
    synth_gates = np.zeros(128, dtype=np.int8)
    if step % 8 < 6:
        synth_gates[(60, 64, 67, 64)[(step // 8) % 4]] = 1
    return {
        'synth/note_gate': synth_gates,
        'synth/velocity': np.full(128, 0.60, dtype=np.float32),
        'synth/parameter_vector': np.asarray([0.3 * math.sin(step / 12)], dtype=np.float32),
        'trombone/note_gate': gates,
        'trombone/velocity': np.full(128, 0.65, dtype=np.float32),
        'trombone/pitch_bend': np.asarray([0.3 * math.sin(step / 6)], dtype=np.float32),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_config = Path(__file__).resolve().parents[1] / 'configs/examples/logic_two_agents.yaml'
    installed_config = Path(sys.prefix) / 'share/logicprogym/configs/logic_two_agents.yaml'
    parser.add_argument('--config', type=Path, default=source_config if source_config.exists() else installed_config)
    parser.add_argument('--steps', type=int, default=0, help='0 runs until Ctrl-C')
    args = parser.parse_args()
    if args.steps < 0:
        parser.error('--steps must be nonnegative')
    options = {} if args.steps == 0 else {'max_episode_steps': args.steps}
    env = gym.make(logicprogym.ENV_ID, config_path=args.config, **options)
    try:
        env.reset()
        print('Track 2: synth notes + Mackie 2 Cutoff. Track 3: trombone notes + pitch bend. MIDI outputs come from your YAML.', flush=True)
        print('Play Track 1. Press Ctrl-C to stop.', flush=True)
        step = 0
        while True:
            action = action_at(step)
            if not env.action_space.contains(action):
                raise ValueError('This example requires the synth/trombone configuration')
            _, reward, terminated, truncated, info = env.step(action)
            notes = np.flatnonzero(action['trombone/note_gate']).tolist()
            synth_notes = np.flatnonzero(action['synth/note_gate']).tolist()
            print(f"step={step + 1} synth held notes={synth_notes} velocity=0.60 "
                  f"Cutoff request={action['synth/parameter_vector'][0]:+.3f} | "
                  f"trombone held notes={notes} velocity=0.65 bend={action['trombone/pitch_bend'][0]:+.3f}", flush=True)
            snapshot = info['snapshot']
            for event in snapshot.events:
                if event.track_id == 'human':
                    print(f'HUMAN {event.kind} {event.values}', flush=True)
            display = snapshot.diagnostics.get('mackie', {}).get('mackie_displays', {}).get('synth')
            for key, reading in snapshot.diagnostics.get('mackie', {}).get('parameter_readings', {}).items():
                value = reading.get('raw', 'unavailable') if reading['valid'] else 'unavailable'
                print(f"Logic {key}: {value}; valid={reading['valid']}; age={reading['age_seconds']}", flush=True)
            if display:
                print(f'Synth LCD cached slot 2: {display[1]!r}', flush=True)
            step += 1
            if terminated or truncated:
                break
            time.sleep(0.25)
    except KeyboardInterrupt:
        print('Stopping...', flush=True)
    finally:
        env.close()
        print('Environment closed.', flush=True)


if __name__ == '__main__':
    main()
