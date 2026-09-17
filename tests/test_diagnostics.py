"""Tests for researcher-facing Logic setup diagnostics."""

from logicprogym.diagnostics import diagnose


def test_doctor_accepts_configured_human_and_agent_ports() -> None:
    results = diagnose(
        "tests/fixtures/configs/logic_split_tracks_test.yaml",
        input_ports=["Test Keyboard"],
        output_ports=["Test Agent Bus"],
    )
    assert not [result for result in results if result.level == "FAIL"]
    assert any(result.subject == "human input" for result in results)
    assert any(result.subject == "agent output" for result in results)
    assert any(result.subject == "Mackie 2" for result in results)


def test_doctor_reports_exact_missing_port_and_available_choices() -> None:
    results = diagnose(
        "tests/fixtures/configs/logic_split_tracks_test.yaml",
        input_ports=["Another Keyboard"],
        output_ports=["Another Bus"],
    )
    failures = [result for result in results if result.level == "FAIL"]
    assert len(failures) == 2
    assert "Test Keyboard" in failures[0].message
    assert "Another Keyboard" in failures[0].message
    assert "Test Agent Bus" in failures[1].message
