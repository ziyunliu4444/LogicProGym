# Maintainer release checks

This checklist is for packaging and release preparation. End users should start
with the [setup guide](logic-setup.md) and [live validation](logic-1.0-acceptance.md).

## Automated checks

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python -m pip check
```

Build a wheel and install it in an isolated environment. Run
`tools/release_smoke.py` with that environment's interpreter from outside the
source checkout. The smoke test checks packaged templates, CLI previews,
example help commands and bundled native sources; it does not open devices.

Check that release archives exclude virtual environments, IDE settings,
personal session files, credentials, recordings and model outputs. Source
archives must retain the fixtures needed by the test suite.

## Live checks

Record the operating system, Logic version, instrument/preset and routing used
for each result in the [live checklist](logic-1.0-acceptance.md). In particular,
frame observations and opt-in resets require live checks before advertising
validated support in a release. Test shutdown and reopening after each relevant configuration.

Do not label a hardware path verified based only on mocked tests. Record the
checks performed and any remaining limitations with each release. Independent simultaneous
Mackie control remains experimental and must not be advertised as fully verified.
