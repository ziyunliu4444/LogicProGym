# Mackie parameter observations

Mackie can report the values displayed by Logic. The environment
exposes accepted numeric readings in `observation['parameter_values']` and
marks them in `observation['parameter_valid']`. Both arrays use the parameter
order in `env.unwrapped.registry.parameters`. For YAML sessions, a track must
include `plugin_parameters` in `observe` to expose its readings. `parameter_mask`
indicates a discovered, selected parameter; it does not indicate a valid reading.
Excluded parameters keep their slots but have zero value, mask, and validity.

An unavailable reading has value zero and validity zero. Always check the
validity mask before interpreting a value; zero can also be a real knob value.
Percentages are divided by 100 (`41.34 %` becomes `0.4134`). Bare numbers retain
their displayed units. Labels, fractions such as `1/16`, and other unit strings
are currently unavailable as numeric observations. User rewards are unchanged.

The numeric parser accepts two ways to establish parameter identity:

- A matching observed track/page header plus complete refreshed name/value cells.
- A matching track/page overview with the configured name in the slot's lower
  cell. Once identified, that slot accepts a complete refreshed numeric value
  even if Logic expands its transient label (for example, `Robotc` → `Robotic`).
  After a complete numeric cell is received, changed-character updates can
  reuse its unchanged characters for that same identified slot. Name-only
  updates neither erase a reading nor refresh its receipt time.

Readings expire after two seconds. Sending a Mackie action clears numeric
readings and partial value fragments; an established overview slot can accept
new complete values without another header. A different observed track/page
clears those slot associations and numeric cell baselines, and environment reset
clears all feedback. Nonnumeric replacement text also clears the numeric baseline.
Text labels and fractions remain raw text with numeric validity false. A valid
reading means recent display feedback; MCU provides no command acknowledgement,
so it does not prove that a particular action caused the value.

Configure a parameter's `id` and exact displayed `name` in the Mackie controller
catalog. Standard IDs such as `synth/page_1/slot_2` provide its address. For custom
IDs, include explicit `page` and `slot` fields in the catalog entry. Long headers
without a visible page number cannot establish this observation context.

The public reading interface works with either adapter:

```python
for reading in logicprogym.parameter_readings(info).values():
    print(reading.id, reading.name, reading.raw, reading.age_seconds)
    if reading.valid:
        print(reading.value)
```

Import `logicprogym` first. `ParameterReading` objects are immutable; `value` is
`None` when numeric validity is false. Raw text may be historical or nonnumeric,
so inspect its age separately. The function reads only the given `info` result
and preserves the environment's observation selection. See the
[observation guide](observations.md#read-instrument-parameters).

For lower-level diagnostics, raw text, name, unit, address, age and validity are available in
`info['snapshot'].diagnostics['parameter_readings']` for Mackie-only sessions,
or `info['snapshot'].diagnostics['mackie']['parameter_readings']` for hybrid
sessions. These dictionaries contain only selected parameters. Unverified cached
LCD/page data is excluded from YAML environment snapshots because it may contain
unrelated state. The public API and multi-agent examples print the selected
readings for human inspection. See [observation selection](yaml-configuration.md#tracks-and-observations).

## Live acceptance

For a configured slot, `parameter_readings` also
includes `display_name` and `display_raw`: the last received LCD text, including labels
and fractions. These fields do not require numeric parsing or a refreshed
track/page header. Raw text alone does not establish numeric validity. Only complete numeric
updates accepted by the identity and age checks populate `parameter_values`. Readings are captured on incoming value-cell updates,
using either the matching displayed name or a slot previously identified from
the configured name on the overview's lower row under a matching track/page
header. This supports Logic changing labels such as `Robotc` to `Robotic` while
showing a value. A different observed track/page clears those slot associations.
Raw readings are retained across later display changes and actions, and cleared on environment
reset. `display_received_at` is the local monotonic receipt time;
`display_age_seconds` reports time since that update, independently of numeric
validity. The shared-track example prints this raw text and age
directly from the `info` returned by `env.step()`.

Configure a mixed session using the [multi-track guide](two-agents-and-training.md).
With the corresponding Mackie endpoints assigned, run:

```bash
python examples/logic_multi_agent.py --config configs/my_multi_session.yaml --steps 100
```

Compare printed valid Cutoff readings with the Track 2 plugin window. Check
that unavailable readings are explicitly labelled and never show another
parameter as Cutoff. Confirm finite completion and Ctrl-C still release notes.
Automated fragment tests do not establish hardware compatibility. Validate
these readings on your session before using them in a reward.
