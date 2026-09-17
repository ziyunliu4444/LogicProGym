"""Invalid model output must never reach a MIDI adapter."""

import numpy as np
import pytest
from logicprogym.actions.compiler import compile_actions
from logicprogym.actions.specs import ActionSpec, ActionRepresentation


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_continuous_action_rejected(value):
    spec = ActionSpec('bend', 'agent', 'midi.pitch_bend', ActionRepresentation.CONTINUOUS)
    with pytest.raises(ValueError, match='finite'):
        compile_actions({'bend': np.array([value])}, [spec])
