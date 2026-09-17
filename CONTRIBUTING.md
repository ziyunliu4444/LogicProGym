# Contributing to LogicProGym

Contributions to code, documentation, examples and reproducible bug reports are
welcome. You do not need Logic Pro to contribute to most Python logic or tests.
Live behavior must be checked separately on macOS with Logic Pro.

## Set up a development checkout

From your clone of the repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
```

The standard installation includes audio and training dependencies, including
PyTorch. The test extra adds pytest. Use a supported Python version listed in
`pyproject.toml`; see [support scope](docs/release-status.md) for live requirements.

Start with the [architecture guide](docs/architecture.md). Public examples are
in `examples/`; files under `tests/fixtures/legacy/` are regression fixtures, not
the recommended starting point for new applications.

## Find a place to contribute

- Clarify a setup step that confused you, or add a small runnable example.
- Reproduce a bug with a fake adapter before changing hardware-facing code.
- Add a test for malformed configuration, action conversion or observation masks.
- Discuss API changes, new dependencies and substantial features in an issue
  before investing in a large implementation.

When adding an example, use a device-neutral YAML template. Put setup details in
YAML and per-run options (steps, checkpoint, evaluation) in command-line flags.
Some older diagnostic helpers retain direct routing flags for compatibility.
Do not silently remove those flags as part of an unrelated cleanup.

## Make a focused pull request

1. Create a branch in your clone or fork and keep the change focused.
2. Add a regression test for a bug fix, or tests for the new behavior.
3. Update the relevant guide and `--help` text if usage changes.
4. Run the affected tests, then the full suite. For example:

   ```bash
   python -m pytest -q tests/test_action_processor.py
   python -m pytest -q
   ```

5. Explain the problem, the change and what you tested in the PR. Clearly state
   when live testing was not performed. Maintainers may need a live test before
   merging hardware-facing changes; contributors need not own every device.

Keep formatting-only work separate from behavior changes. Prefer descriptive
names, small functions and docstrings at public boundaries. Comments should
explain units, ownership, timing and surprising decisions—not restate each line.
Use type annotations for new public APIs where practical.

## Preserve the safety and compatibility boundaries

- Constructing an environment must not open MIDI or audio devices; reset connects.
- Never send live MIDI from automated tests. Use injectable fake backends.
- Keep human and agent routes separate. Do not reset unowned controls.
- Missing or stale feedback is not zero and is not confirmed state.
- Do not put forced process exit in the reusable environment. CLI supervision
  has different responsibilities; see [shutdown](docs/shutdown.md).
- Preserve public action IDs, shapes, units, YAML meanings and checkpoint
  compatibility unless the PR explicitly proposes a migration.
- Do not commit personal YAML, recordings, checkpoints, Logic projects or
  third-party instrument samples. Use synthetic test data and placeholder devices.

## Report a live bug

Include the command, traceback, expected/actual behavior, Python/package version,
macOS and Logic versions, and a sanitized configuration. For MIDI, include the
port mapping, wire channel (1–16), CC number and assignment target. For Mackie,
include track/page/slot and feedback diagnostics. For audio, include rate and
validity/gap diagnostics. Do not post private recordings or device names unless
you intend to share them.

Use the [live checklist](docs/logic-1.0-acceptance.md) for relevant changes. Work
in a backed-up test project at a comfortable volume. A fake-backend test is not
evidence that a particular Logic instrument responded correctly.

## Packaging changes

When adding public scripts or templates, review the packaged folder lists in
`pyproject.toml`, `MANIFEST.in` and `tools/release_smoke.py` as applicable. Follow
[release checks](docs/final-check.md) to verify installed files outside the source
checkout. Do not publish packages or change the release version as part of an
unrelated PR.

Contributions are intended for distribution under this repository's MIT license.
Discuss disagreements respectfully and provide concrete reproductions where possible.
