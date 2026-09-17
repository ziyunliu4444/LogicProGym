# Mackie parameter observations

Mackie can report the values displayed by Logic. The environment
exposes accepted numeric readings in `observation['parameter_values']` and
marks them in `observation['parameter_valid']`. Both arrays use the parameter
order in `env.unwrapped.registry.parameters`. `parameter_mask` indicates that
a parameter exists; it does not indicate a valid reading.

An unavailable reading has value zero and validity zero. Always check the
validity mask before interpreting a value; zero can also be a real knob value.
Percentages are divided by 100 (`41.34 %` becomes `0.4134`). Bare numbers retain
their displayed units. Labels, fractions such as `1/16`, and other unit strings
are currently unavailable as numeric observations. User rewards are unchanged.

The parser requires an observed track/page header, the configured parameter
name in its slot, and complete refreshed name and value cells. Readings expire
after two seconds. Sending a Mackie action clears the observation context until
another header is received. A valid reading means a recent, matched display
reading; MCU provides no command acknowledgement, so it does not prove that a
particular action caused the value. Delayed or incomplete updates can result in
unavailable observations even while the knob visibly moves.

Configure a parameter's `id` and exact displayed `name` in the Mackie controller
catalog. Standard IDs such as `synth/page_1/slot_2` provide its address. For custom
IDs, include explicit `page` and `slot` fields in the catalog entry. Long headers
without a visible page number cannot establish this observation context.

Raw text, name, unit, address, age and validity are available in
`info['snapshot'].diagnostics['parameter_readings']` for Mackie-only sessions,
or `info['snapshot'].diagnostics['mackie']['parameter_readings']` for hybrid
sessions. General cached LCD output remains available separately. The public
API and multi-agent examples print the accepted readings for human inspection.

## Live acceptance

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
