# Maintainer release checklist

This checklist is for packaging and release preparation. End users should start
with the [setup guide](logic-setup.md) and [live validation](live-testing.md).

## Automated checks

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m pip check
```

## Build and check an installed wheel

Run from the repository root with the development virtual environment active:

```bash
python -m pip install build
PROJECT_DIR="$PWD"
VERIFY_DIR="$(mktemp -d /tmp/logicprogym-verify.XXXXXX)"
python -m build --outdir "$VERIFY_DIR/dist" .
python -m venv "$VERIFY_DIR/venv"
"$VERIFY_DIR/venv/bin/python" -m pip install "$VERIFY_DIR"/dist/*.whl
cd "$VERIFY_DIR"
"$VERIFY_DIR/venv/bin/python" -m pip check
"$VERIFY_DIR/venv/bin/python" -c 'import logicprogym; print(logicprogym.__file__)'
"$VERIFY_DIR/venv/bin/python" "$PROJECT_DIR/tools/release_smoke.py"
cd "$PROJECT_DIR"
```

The printed import path must point into the temporary environment, not `src/`
in your checkout. A fresh output directory avoids selecting an older wheel.
Installation requires access to dependency packages. Keep the temporary folder
until you have reviewed the results; these commands do not publish a release.

The smoke test discovers all installed YAML templates, checks that both packaged
template locations agree, constructs their environments without reset, runs CLI
previews and inspector/scanner help, and checks example/tool/live-test help and
bundled native sources. Every template is constructed through `gym.make`.
Action-free templates, including discovery and the frame observer, use
`Discrete(1)` with `step(0)` for observation-only runs. No MIDI ports or audio
devices are opened during this check.

## Inspect the archives

Check that release archives exclude virtual environments, IDE settings,
personal session files, credentials, recordings and model outputs. Source
archives must retain the fixtures needed by the test suite.
For example, using the temporary build directory above:

```bash
python -m zipfile -l "$VERIFY_DIR"/dist/*.whl
tar -tzf "$VERIFY_DIR"/dist/*.tar.gz
```

Record the commit, package version, automated results, and installed-wheel result
for the release. Rebuild after changing files; a successful older wheel check
does not validate a later source checkout.

## Live checks

Record the operating system, Logic version, instrument/preset and routing used
for each result in the [live checklist](live-testing.md). In particular,
frame observations and opt-in resets require live checks before advertising
validated support in a release. Test shutdown and reopening after each relevant configuration.

Do not label a hardware path verified based only on mocked tests. Record the
checks performed and any remaining limitations with each release. Independent simultaneous
Mackie control remains experimental and must not be advertised as fully verified.
