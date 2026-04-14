from pathlib import Path

from hosaka.setup.orchestrator import build_default_orchestrator


def test_orchestrator_resume_and_progress(tmp_path: Path) -> None:
    orchestrator = build_default_orchestrator(tmp_path / "state.json")
    assert orchestrator.summary()["step_index"] == 1

    orchestrator.set_field("hostname", "hosaka-demo")
    orchestrator.next_step()

    resumed = build_default_orchestrator(tmp_path / "state.json")
    summary = resumed.summary()
    assert summary["hostname"] == "hosaka-demo"
    assert summary["step_index"] == 2
    assert summary["progress_percent"] > 0


def test_orchestrator_invalid_step_and_empty_defaults(tmp_path: Path) -> None:
    orchestrator = build_default_orchestrator(tmp_path / "state.json")
    orchestrator.state.current_step = "not-a-real-step"
    assert orchestrator.step_index == 0

    orchestrator.set_field("hostname", "")
    orchestrator.set_field("workspace_root", "")
    orchestrator.set_field("theme", "")

    summary = orchestrator.summary()
    assert summary["hostname"] == "hosaka-field-terminal"
    assert summary["workspace_root"] == "/opt/hosaka/workspace"
    assert summary["theme"] == "dark"
