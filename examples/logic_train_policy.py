"""Checkpointed pitch-imitation training through the public Gymnasium API.

The human supplies the target pitch; a categorical policy chooses an agent
pitch. This demonstrates task composition and checkpoints, not audio-quality
optimization. It leaves plugin parameter movements at zero.
"""

import argparse
from pathlib import Path
import time

import gymnasium as gym
import numpy as np
import torch

import logicprogym
from logicprogym.tasks import PitchCutoffTask
from logicprogym.checkpoints import session_metadata, validate_session
from logicprogym.example_support import make_action, supervise



def main(on_cleanup=None):
    """Train/evaluate one run; the optional hook signals CLI cleanup only.

    ``args`` holds command-line settings, not policy actions. Routing and action
    definitions come from the session YAML; steps/checkpoints are per-run choices.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config')
    parser.add_argument('--track', default='agent')
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--checkpoint', type=Path, default=Path('artifacts/pitch_policy.pt'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--evaluate', action='store_true')
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('--steps must be positive')
    if args.evaluate and not args.resume:
        parser.error('--evaluate requires --resume')
    torch.manual_seed(args.seed)
    policy = torch.nn.Sequential(torch.nn.Linear(1, 32), torch.nn.Tanh(), torch.nn.Linear(32, 128))
    optimizer = torch.optim.Adam(policy.parameters(), lr=0.003)
    completed = 0
    baseline = 0.0
    session = session_metadata(args.config)
    if args.resume:
        # Resume learning state, not the instrument state in Logic. Session
        # validation rejects incompatible YAML before any ports are opened.
        saved = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
        validate_session(saved, session)
        if saved['version'] != 1 or saved['track'] != args.track:
            raise ValueError('Checkpoint version or agent track does not match')
        policy.load_state_dict(saved['policy'])
        optimizer.load_state_dict(saved['optimizer'])
        torch.set_rng_state(saved['rng'])
        completed, baseline = saved['steps'], saved['baseline']
    # Freeze the target before sending the action, so incoming note-off events
    # cannot change which target the action is evaluated against.
    target = None

    def reward(observation, action, info):
        # This deliberately simple task rewards pitch imitation, not timbre.
        notes = np.flatnonzero(action[f'{args.track}/note_gate'])
        return 0.0 if target is None or len(notes) == 0 else -abs(int(notes[0]) - target) / 127.0

    env = gym.make(logicprogym.ENV_ID, config_path=args.config, max_episode_steps=args.steps)
    env = logicprogym.FunctionReward(env, reward)
    env = gym.wrappers.RecordEpisodeStatistics(env)
    task = PitchCutoffTask()
    try:
        observation, info = env.reset(seed=args.seed)
        # Validate the action schema before sending any notes.
        make_action(env.action_space, args.track, 60)
        for _ in range(args.steps):
            target = task.human_note(observation)
            note = None
            distribution = None
            if target is not None:
                logits = policy(torch.tensor([target / 127.0], dtype=torch.float32))
                distribution = torch.distributions.Categorical(logits=logits)
                selected = logits.argmax() if args.evaluate else distribution.sample()
                note = int(selected)
            observation, score, terminated, truncated, info = env.step(
                make_action(env.action_space, args.track, note)
            )
            if distribution is not None and not args.evaluate:
                loss = -distribution.log_prob(selected) * (score - baseline)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                baseline = 0.95 * baseline + 0.05 * score
            completed += 1
            print(f'step={completed} human={target} agent={note} reward={score:+.4f}', flush=True)
            if terminated or truncated:
                print(f"Episode: {info.get('episode')}", flush=True)
                break
            time.sleep(0.25)
    except KeyboardInterrupt:
        print('Stopping...', flush=True)
    finally:
        try:
            # Persist before entering native port cleanup, which can stall.
            if not args.evaluate:
                args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.checkpoint.with_suffix('.tmp')
                torch.save(dict(version=1, session=session, track=args.track, policy=policy.state_dict(),
                                optimizer=optimizer.state_dict(), rng=torch.get_rng_state(),
                                steps=completed, baseline=baseline), temporary)
                temporary.replace(args.checkpoint)
                print(f'Saved {args.checkpoint}', flush=True)
        finally:
            print('Stopping agent and releasing MIDI notes...', flush=True)
            if on_cleanup is not None:
                on_cleanup()
            env.close()
            print('Environment closed.', flush=True)


def _training_worker(connection):
    """Run normally; notify the supervisor before potentially blocking cleanup."""
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()




if __name__ == '__main__':
    raise SystemExit(supervise(_training_worker))
