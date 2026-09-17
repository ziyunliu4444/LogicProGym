"""Safety behavior for the not-yet-implemented Logic Pro adapter."""

import pytest

from logicprogym.adapters.logic import LogicAdapter


def test_logic_adapter_does_not_claim_a_fake_connection():
    """An unfinished adapter must fail clearly instead of dropping commands."""

    with pytest.raises(NotImplementedError, match="not been implemented"):
        LogicAdapter().connect()
