"""Exercise configured tracks through the public API with graceful cleanup.

Run after installing logicprogym: python live_tests/logic_public_api.py CONFIG.yaml
This explicit hardware test samples every configured action, including notes
and knobs. Start with quiet monitoring levels and a suitable test project.
"""

import argparse
import time

import gymnasium as gym
import logicprogym
from logicprogym.config import LogicProGymConfig


def print_transition(step, reward, action, info, config):
    """Separate requested actions from cached, asynchronous Logic feedback."""
    print(f"\nstep={step} reward={reward:.4f}", flush=True)
    if "timing" in info:
        print("  timing:", info["timing"], flush=True)
    snapshot = info.get('snapshot')
    diagnostics = {} if snapshot is None else snapshot.diagnostics
    mackie = diagnostics.get('mackie', diagnostics)
    displays = mackie.get('mackie_displays', {})
    pages = mackie.get('mackie_pages', {})
    for parameter_id, reading in mackie.get('parameter_readings', {}).items():
        value = reading.get('raw', 'unavailable') if reading['valid'] else 'unavailable'
        print(f"  Logic parameter {parameter_id} ({reading['name']}): {value} "
              f"valid={reading['valid']} age={reading['age_seconds']}", flush=True)
    settings = config.adapter.get('mackie', config.adapter)
    maximum = int(settings.get('max_steps_per_action', 8))
    deadzone = float(settings.get('relative_deadzone', 0.1))
    assignments = {item['id']: item for item in settings.get('controllers', ()) if 'id' in item}
    for track in config.tracks:
        prefix = track.alias + '/'
        values = {key[len(prefix):]: value for key, value in action.items() if key.startswith(prefix)}
        if not values:
            continue
        assignment = assignments.get(track.alias, {})
        print(f"  {track.alias} | Logic track={assignment.get('track', '?')} "
              f"Mackie={assignment.get('controller', '?')}", flush=True)
        gate = values.get('note_gate')
        if gate is not None:
            notes = [i for i, value in enumerate(gate) if value]
            velocities = values.get('velocity')
            text = ', '.join(
                f"{note} (velocity={float(velocities[note]):.2f})" if velocities is not None else str(note)
                for note in notes
            )
            print(f"    requested held notes: {text or 'none'}", flush=True)
        for name in ('pitch_bend', 'expression', 'sustain'):
            if name in values:
                print(f"    requested {name}={float(values[name][0]):+.3f}", flush=True)
        for spec in track.actions:
            if spec.target != 'plugin.relative_vector':
                requested = action[spec.id]
                if spec.target == 'midi.note_gate':
                    requested = [i for i, held in enumerate(requested) if held]
                elif getattr(requested, 'size', 1) > 8:
                    requested = f'array shape={requested.shape}, min={requested.min():.3f}, max={requested.max():.3f}'
                print(f'    action {spec.id} ({spec.target}) = {requested}', flush=True)
            if spec.target != 'plugin.relative_vector':
                continue
            for amount, binding in zip(action[spec.id], spec.encoding.get('parameters', ())):
                amount = float(amount)
                ticks = 0 if abs(amount) <= deadzone else max(1, round(abs(amount) * maximum)) * (1 if amount > 0 else -1)
                print(f"    requested page={binding['page']} slot={binding['slot']} "
                      f"action={amount:+.3f} V-Pot ticks={ticks:+d}", flush=True)
        display = displays.get(track.alias)
        if display is None:
            print('    Logic LCD: unavailable', flush=True)
        else:
            cells = ' | '.join(f'{i}: {upper!r}/{lower!r}' for i, (upper, lower) in enumerate(display, 1) if upper or lower)
            print(f"    Logic LCD (cached; page={pages.get(track.alias, '?')}): {cells}", flush=True)
    if snapshot is not None:
        for event in snapshot.events:
            if event.track_id not in assignments:
                print(f"  INPUT {event.track_id}: {event.kind} {event.values}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--manifest", help="Save a new run manifest JSON; never overwrite")
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("steps must be positive")
    config = LogicProGymConfig.from_yaml(args.config)
    if args.manifest:
        from logicprogym.experiments import write_manifest
        write_manifest(args.manifest, args.config, seed=args.seed,
                       labels={"policy": "bounded random smoke-test policy", "requested_steps": args.steps})
    env = gym.make(logicprogym.ENV_ID, config_path=args.config,
                   max_episode_steps=args.steps)
    env = gym.wrappers.RecordEpisodeStatistics(env)
    try:
        env.reset(seed=args.seed)
        env.action_space.seed(args.seed)
        for step in range(args.steps):
            action = env.action_space.sample()
            # Limit this smoke test to one note per configured note-gate track.
            for spec in config.actions:
                if spec.target == 'midi.note_gate':
                    value = action[spec.id]
                    value[...] = 0
                    value[60] = 1
            _, reward, terminated, truncated, info = env.step(action)
            print_transition(step + 1, reward, action, info, config)
            if terminated or truncated:
                print(f"Episode: {info.get('episode')}", flush=True)
                break
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Stopping...", flush=True)
    finally:
        env.close()
        print("Environment closed.", flush=True)


if __name__ == "__main__":
    main()
