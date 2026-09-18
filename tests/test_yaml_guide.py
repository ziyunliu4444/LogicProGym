"""Keep the tutorial's complete configurations constructible without hardware."""
from pathlib import Path
import re

import logicprogym
from logicprogym.actions.processor import ActionProcessor


def test_yaml_tutorial_complete_examples(tmp_path):
    guide = Path('docs/yaml-configuration.md').read_text()
    examples = re.findall(r'```yaml\n(.*?)```', guide, re.S)
    assert len(examples) == 4
    for index, content in enumerate(examples):
        path = tmp_path / f'example_{index}.yaml'
        path.write_text(content)
        env = logicprogym.make(path)
        try:
            action = env.action_space.sample()
            assert env.action_space.contains(action)
            ActionProcessor(env.unwrapped.action_specs).process(action)
            if index == 2:
                commands = ActionProcessor(env.unwrapped.action_specs).process({'agent/cutoff': 1})
                assert commands[0].values['value'] == 0.5
        finally:
            env.close()  # No reset: no MIDI/audio devices are opened.
