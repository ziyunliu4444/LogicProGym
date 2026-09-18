"""Human plays notes while a scripted agent moves shared-instrument parameters.

No agent notes are sent.
This is a deterministic musical demonstration, not a trained policy. Verify all
eight mapped parameters first: some instruments have sound-generating controls.
"""
import math
import re
import time
from dataclasses import replace
import numpy as np
from logicprogym.example_support import run_demo, supervise


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
    snapshot = info.get('snapshot')
    diagnostics = {} if snapshot is None else snapshot.diagnostics
    readings = diagnostics.get('mackie', diagnostics).get('parameter_readings', {})
    if not readings:
        print('KNOBS no selected readings; enable plugin_parameters in shared.observe.', flush=True)
        return
    for parameter_id, reading in readings.items():
        name = reading.get('name', parameter_id)
        raw = reading.get('raw')
        age = reading.get('age_seconds')
        age_text = '' if age is None else f' age={age:.2f}s'
        if reading.get('valid') and raw is not None:
            status = f"reported={raw!r} valid=True{age_text}"
        elif reading.get('display_raw') is not None:
            status = (f"displayed={reading['display_raw']!r} "
                      'unverified track/page; cached LCD, freshness unknown')
        elif raw is not None:
            status = f"unavailable last_reported={raw!r} valid=False{age_text}"
        else:
            status = 'waiting for matched numeric feedback'
        print(f'KNOB {name} [{parameter_id}] {status}', flush=True)


def main(on_cleanup=None):
    run_demo(agent_action, __doc__, on_cleanup=on_cleanup,
             on_step=print_after_feedback, allow_read_only=True)


def print_after_feedback(info, env, *, feedback_seconds=0.3):
    """Collect asynchronous feedback after movement, before the next action.

    Read only the Mackie cache: never drain human MIDI, send probe movements,
    or create extra Gymnasium steps. Keep the existing observation selection
    and identity/age checks. This monitor does not alter the step's reward.
    """
    base = env.unwrapped
    mackie = getattr(base.adapter, 'mackie', None)
    if mackie is None:
        print_parameter_readings(info)
        return
    snapshot = info.get('snapshot')
    if snapshot is None:
        return
    # A batch can briefly expose several different parameter readings. Preserve
    # each accepted report from this window rather than only its final LCD state.
    reports = dict(snapshot.diagnostics.get('mackie', {}).get('parameter_readings', {}))
    deadline = time.monotonic() + feedback_seconds
    while True:
        selected = base._select_snapshot(mackie.receive())
        for key, reading in selected.diagnostics.get('parameter_readings', {}).items():
            previous = reports.get(key, {})
            if not reading.get('valid') and previous.get('raw') is not None:
                # Keep a historical report visible, but never keep its validity
                # after the decoder invalidates the current display context.
                reports[key] = dict(previous, valid=False)
            else:
                reports[key] = reading
        collect_display_text(mackie, reports)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.02, remaining))
    # Reports describe the time they arrived, not a guarantee that all knobs
    # remain at these values or that every movement generated feedback.
    now = time.monotonic()
    reports = {key: dict(reading, age_seconds=max(0., now-reading['received_at']))
               if reading.get('received_at') is not None else reading
               for key, reading in reports.items()}
    print_parameter_readings({'snapshot': replace(snapshot, diagnostics={
        'mackie': {'parameter_readings': reports}})})


def collect_display_text(mackie, reports):
    """Add terminal-only LCD text without promoting it to an observation.

    Logic may show a value without refreshing the identity header required by
    the verified reader. Only inspect selected bindings with a matching name;
    never derive a percentage from an action or an encoder-ring position.
    """
    service = getattr(mackie, 'service', None)
    bridge = getattr(service, 'bridge', None)
    if bridge is None:
        return
    for binding in mackie.feedback_bindings:
        reading = reports.get(binding['id'])
        if reading is None or reading.get('valid'):
            continue
        controller = bridge.pool.controllers[binding['controller'] - 1]
        name, raw = controller.lcd.strips[binding['slot'] - 1]
        if (name.casefold() == binding['name'].casefold()
                and re.fullmatch(r'[+-]?\d+(?:\.\d+)?\s*%?', raw.strip())):
            reports[binding['id']] = dict(reading, display_raw=raw)


def _worker(connection):
    try:
        main(on_cleanup=lambda: connection.send('cleanup'))
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(supervise(_worker))
