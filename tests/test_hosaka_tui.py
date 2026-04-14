from pathlib import Path

import pytest

pytest.importorskip("rich")

from hosaka.setup.orchestrator import build_default_orchestrator
from hosaka.tui import terminal


def test_tui_input_disables_markup_for_bracket_prompts(tmp_path: Path, monkeypatch) -> None:
    orchestrator = build_default_orchestrator(tmp_path / "state.json")
    orchestrator.state.current_step = "configure_workspace_root"

    calls: list[dict] = []

    def fake_input(prompt: str, markup: bool = True) -> str:
        calls.append({"prompt": prompt, "markup": markup})
        raise EOFError

    monkeypatch.setattr(terminal.console, "input", fake_input)
    monkeypatch.setattr(terminal.console, "print", lambda *args, **kwargs: None)

    terminal.run_setup_flow(orchestrator, "http://127.0.0.1:8421")

    assert calls, "Expected console.input to be called"
    assert calls[0]["markup"] is False
    assert "[/opt/hosaka/workspace]" in calls[0]["prompt"]
