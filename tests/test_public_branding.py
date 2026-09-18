"""Keep public source and documentation consistent with the release name."""
from pathlib import Path
import re


def test_public_files_use_current_project_name():
    root = Path(__file__).resolve().parents[1]
    # Separate tokens keep this regression test from matching its own source.
    obsolete = re.compile(r'(?:' + '|'.join(('daw', 'trombone')) + r')[\s_-]*gym', re.I)
    paths = [root / name for name in (
        'LICENSE', 'README.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
        'pyproject.toml', 'MANIFEST.in', '.gitignore')]
    for folder in ('src/logicprogym', 'docs', 'examples', 'configs/examples',
                   'tools', 'live_tests', 'protocol', 'tests', '.github'):
        paths.extend(path for path in (root / folder).rglob('*')
                     if path.is_file() and path.suffix in
                     {'.py', '.md', '.yaml', '.yml', '.toml', '.plist', '.swift', '.svg'})
    failures = []
    for path in paths:
        if obsolete.search(str(path.relative_to(root))):
            failures.append(str(path.relative_to(root)))
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if obsolete.search(line):
                failures.append(f'{path.relative_to(root)}:{number}')
    assert not failures, 'Outdated public branding: ' + ', '.join(failures)
    assert 'Copyright (c) 2026 LogicProGym contributors' in (root / 'LICENSE').read_text()
