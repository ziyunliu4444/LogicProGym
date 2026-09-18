"""Regression fixture for pitch-conditioned cutoff learning.

Retained for automated compatibility tests, not as a public learning example.
See examples/README.md for supported demonstrations and setup walkthroughs.
The fixture mirrors the highest held note one octave lower and learns relative
Cutoff movement on a separate agent track.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).parents[1]
PROJECT_SRC = PROJECT_ROOT / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from logicprogym.adapters.logic_hybrid import LogicHybridAdapter
from logicprogym.config import LogicProGymConfig
from logicprogym.env import LogicProEnv
from logicprogym.models import DawCommand
from logicprogym.tasks import PitchCutoffTask


CONFIG = PROJECT_ROOT / "configs" / "logic_split_tracks_test.yaml"
MACKIE_FEEDBACK_SETTLE_SECONDS = 0.04


def cutoff_from_strips(strips) -> tuple[float, str] | None:
    """Return Logic's named Cutoff as a raw 0..100 percentage."""

    if strips is None:
        return None
    name, raw = (cell.strip() for cell in strips[1])
    if name.lower() != "cutoff":
        return None
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", raw)
    if match is None:
        return None
    return float(match.group()), raw


def cutoff_from_mackie(info: dict[str, object]) -> tuple[float, str] | None:
    """Read Logic's actual named Cutoff value from Mackie 2's LCD."""

    snapshot = info["snapshot"]
    displays = snapshot.diagnostics.get("mackie", {}).get("mackie_displays", {})
    return cutoff_from_strips(displays.get("agent"))


def current_cutoff_from_bridge(env: LogicProEnv) -> tuple[float, str] | None:
    """Read the latest coalesced Mackie feedback after Logic's partial updates."""

    bridge = env.adapter.mackie.service.bridge
    return None if bridge is None else cutoff_from_strips(bridge.parameters("agent"))


def action_steps(action: float, deadzone: float = 0.1, maximum: int = 4) -> int:
    """Mirror the adapter's continuous-action to integer-V-Pot conversion."""

    if abs(action) <= deadzone:
        return 0
    steps = max(1, round(abs(action) * maximum))
    return steps if action > 0 else -steps


def transition_reward(
    previous_percent: float,
    current_percent: float,
    target_percent: float,
) -> tuple[float, float, float]:
    """Reward progress toward the target plus a small remaining-error cost."""

    previous_error = abs(previous_percent - target_percent)
    current_error = abs(current_percent - target_percent)
    improvement = (previous_error - current_error) / 100.0
    proximity_penalty = 0.05 * ((current_error / 100.0) ** 2)
    return improvement - proximity_penalty, improvement, proximity_penalty


def release_agent_notes(env: LogicProEnv) -> None:
    """Silence the agent without entering CoreMIDI's occasionally stuck close."""

    commands = env.action_processor.reset()
    commands.extend(
        [
            DawCommand("agent", "midi.cc.64", {"value": 0.0}),
            DawCommand("agent", "midi.all_notes_off", {}),
            DawCommand("agent", "midi.all_sound_off", {}),
        ]
    )
    env.backend.apply(commands)


def mackie_feedback_summary(info: dict[str, object]) -> str:
    """Describe the exact Mackie 2 state when cutoff parsing is unavailable."""

    diagnostics = info["snapshot"].diagnostics.get("mackie", {})
    display = diagnostics.get("mackie_displays", {}).get("agent")
    page = diagnostics.get("mackie_pages", {}).get("agent")
    if display is None:
        return "no Mackie 2 LCD feedback"
    return f"page={page!r} slot2={display[1]!r}"


def print_human_events(info: dict[str, object]) -> None:
    """Print each new MIDI event received from the human keyboard."""

    for event in info["snapshot"].events:
        if event.track_id == "human":
            print(f"HUMAN {event.kind} {event.values}", flush=True)


class CutoffPolicy(torch.nn.Module):
    """Gaussian actor mapping pitch plus cutoff state to relative movement."""

    def __init__(self) -> None:
        super().__init__()
        self.network = torch.nn.Sequential(
            torch.nn.Linear(2, 16),
            torch.nn.Tanh(),
            torch.nn.Linear(16, 1),
        )
        self.log_std = torch.nn.Parameter(torch.tensor([-1.2]))

    def distribution(self, features: torch.Tensor) -> torch.distributions.Normal:
        return torch.distributions.Normal(
            torch.tanh(self.network(features)), self.log_std.exp()
        )


def gym_action(note: int | None, cutoff_action: float) -> dict[str, np.ndarray]:
    """Build agent MIDI and two-knob vectors; only slot 2 controls Cutoff."""

    gates = np.zeros(128, dtype=np.int8)
    if note is not None:
        gates[max(0, note - 12)] = 1
    return {
        "agent/note_gate": gates,
        "agent/velocity": np.full(128, 0.60, dtype=np.float32),
        "agent/pitch_bend": np.asarray([0.0], dtype=np.float32),
        "agent/expression": np.asarray([0.75], dtype=np.float32),
        "agent/sustain": np.asarray([0.0], dtype=np.float32),
        "agent/parameter_vector": np.asarray([0.0, cutoff_action], dtype=np.float32),
    }


def run(control_hz: float, learning_rate: float, max_steps: int) -> None:
    """Train until Ctrl-C or the optional finite step limit."""

    config = LogicProGymConfig.from_yaml(CONFIG)
    env = LogicProEnv.from_config(LogicHybridAdapter.from_config(config.adapter), config)
    task = PitchCutoffTask()
    policy = CutoffPolicy()
    optimizer = torch.optim.Adam(policy.parameters(), lr=learning_rate)
    interval = 1.0 / control_hz
    baseline = 0.0
    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_requested.set()

    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(handled_signal, request_stop)

    step = 0
    try:
        observation, info = env.reset()
        print("Play the piano on Logic Track 1.")
        print("The Track 2 synth mirrors one octave lower and learns actual Cutoff (slot 2).")
        previous_cutoff_percent: float | None = None
        while not stop_requested.is_set() and (max_steps <= 0 or step < max_steps):
            started = time.monotonic()
            print_human_events(info)
            note = task.human_note(observation)
            cutoff_action = 0.0
            policy_step = False
            if note is not None:
                cutoff_feedback = cutoff_from_mackie(info)
                # Readback improves the policy input when present, but never
                # gates control. Zero is only a neutral "unknown" feature; it
                # is not integrated or treated as an observed cutoff value.
                observed_cutoff = (
                    previous_cutoff_percent
                    if previous_cutoff_percent is not None
                    else (None if cutoff_feedback is None else cutoff_feedback[0])
                )
                cutoff_feature = (
                    0.0 if observed_cutoff is None else observed_cutoff / 50.0 - 1.0
                )
                features = torch.as_tensor(
                    [task.pitch_target(note), cutoff_feature], dtype=torch.float32
                )
                distribution = policy.distribution(features)
                raw_action = distribution.sample()
                cutoff_action = float(torch.tanh(raw_action).item())
                # Keep exploratory output above the configured Mackie
                # deadzone so an active policy step always emits V-Pot ticks.
                if abs(cutoff_action) <= 0.1:
                    cutoff_action = math.copysign(0.11, cutoff_action or 1.0)
                policy_step = True
            observation, _unused, _terminated, _truncated, info = env.step(
                gym_action(note, cutoff_action)
            )
            stop_requested.wait(MACKIE_FEEDBACK_SETTLE_SECONDS)
            cutoff_feedback = current_cutoff_from_bridge(env)
            if note is not None and cutoff_feedback is None:
                print(
                    f"step={step} input_pitch={note} "
                    f"agent_pitch={max(0, note - 12)} "
                    f"cutoff_action={cutoff_action:+.3f} "
                    f"mackie_steps={action_steps(cutoff_action):+d} "
                    "cutoff_actual=unavailable reward=unavailable "
                    f"mackie=({mackie_feedback_summary(info)})",
                    flush=True,
                )
            elif note is not None and cutoff_feedback is not None:
                cutoff_percent, _raw_cutoff = cutoff_feedback
                target_percent = note / 127.0 * 100.0
                error_percent = cutoff_percent - target_percent
                if previous_cutoff_percent is None:
                    previous_cutoff_percent = cutoff_percent
                    print(
                        f"step={step} input_pitch={note} "
                        f"agent_pitch={max(0, note - 12)} "
                        f"cutoff_action={cutoff_action:+.3f} "
                        f"mackie_steps={action_steps(cutoff_action):+d} "
                        f"cutoff_actual={cutoff_percent:.2f}% "
                        f"target={target_percent:.2f}% reward=warming_up",
                        flush=True,
                    )
                    step += 1
                    if max_steps > 0 and step >= max_steps:
                        print(f"Completed {max_steps} steps.", flush=True)
                        break
                    stop_requested.wait(
                        max(0.0, interval - (time.monotonic() - started))
                    )
                    continue
                reward, improvement, proximity_penalty = transition_reward(
                    previous_cutoff_percent, cutoff_percent, target_percent
                )
                previous_cutoff_percent = cutoff_percent
                if policy_step:
                    baseline = 0.95 * baseline + 0.05 * reward
                    advantage = reward - baseline
                    loss = -distribution.log_prob(raw_action).sum() * advantage
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                print(
                    f"step={step} input_pitch={note} "
                    f"agent_pitch={max(0, note - 12)} "
                    f"cutoff_action={cutoff_action:+.3f} "
                    f"mackie_steps={action_steps(cutoff_action):+d} "
                    f"cutoff_actual={cutoff_percent:.2f}% "
                    f"target={target_percent:.2f}% error={error_percent:+.2f}pp "
                    f"improvement={improvement:+.4f} "
                    f"proximity_cost={proximity_penalty:.4f} reward={reward:+.4f}",
                    flush=True,
                )
            step += 1
            if max_steps > 0 and step >= max_steps:
                print(f"Completed {max_steps} steps.", flush=True)
                break
            stop_requested.wait(max(0.0, interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        stop_requested.set()
    finally:
        print("Stopping agent and releasing MIDI notes...", flush=True)
        try:
            release_agent_notes(env)
        except BaseException as error:
            print(f"MIDI panic warning: {error}", flush=True)
        print("Agent stopped.", flush=True)
        # CoreMIDI can block indefinitely while closing virtual endpoints.
        # Process exit lets macOS reclaim them after the panic messages above.
        os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-hz", type=float, default=4.0)
    parser.add_argument("--learning-rate", type=float, default=0.003)
    parser.add_argument("--steps", type=int, default=0, help="0 runs until Ctrl-C")
    args = parser.parse_args()
    if args.control_hz <= 0 or args.learning_rate <= 0 or args.steps < 0:
        parser.error("control rate and learning rate must be positive; steps cannot be negative")
    run(args.control_hz, args.learning_rate, args.steps)


if __name__ == "__main__":
    main()
