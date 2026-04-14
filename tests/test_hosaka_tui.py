from pathlib import Path

from hosaka.setup.orchestrator import build_default_orchestrator
from hosaka.tui import terminal


def test_tui_bracket_prompt_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    orchestrator = build_default_orchestrator(tmp_path / "state.json")
    orchestrator.state.current_step = "configure_workspace_root"

    calls: list[str] = []

    def fake_input(prompt: str) -> str:
        calls.append(prompt)
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    terminal.run_setup_flow(orchestrator, "http://127.0.0.1:8421")

    assert calls, "Expected input to be called"
    assert "[/opt/hosaka/workspace]" in calls[0]
