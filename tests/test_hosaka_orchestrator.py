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
