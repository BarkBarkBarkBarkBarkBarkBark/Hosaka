import pytest

from hosaka import main_console
from hosaka.tui import style as tui_style


def test_resolve_manifest_alias() -> None:
    target = main_console._resolve_read_target("manifest", current_dir=main_console.APP_ROOT)
    assert target == main_console.MANIFEST_DOC


def test_unknown_command_shows_no_wrong_way(capsys) -> None:
    main_console._unknown_command("bogus")
    captured = capsys.readouterr()
    assert "No Wrong Way" in captured.out
    assert "/commands" in captured.out


def test_change_directory_relative_path(tmp_path) -> None:
    sub = tmp_path / "alpha"
    sub.mkdir()
    out = main_console._change_directory("alpha", current_dir=tmp_path)
    assert out == sub


def test_report_command_error_keeps_operator_in_tui(capsys, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOSAKA_LOG_FILE", str(tmp_path / "boot.log"))
    main_console._report_command_error("/net", RuntimeError("nope"))
    out = capsys.readouterr().out
    assert "Something broke in /net" in out
    assert "/logs" in out
    assert "still here" in out
    assert "nope" in (tmp_path / "boot.log").read_text()


def test_show_logs_tails_file(capsys, tmp_path, monkeypatch) -> None:
    log = tmp_path / "boot.log"
    log.write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setenv("HOSAKA_LOG_FILE", str(log))
    main_console._show_logs(lines=2)
    out = capsys.readouterr().out
    assert "two" in out
    assert "three" in out
    assert "one" not in out


def test_update_flow_prints_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(main_console, "run_update", lambda: (True, "updated"))
    main_console._run_update_flow()
    out = capsys.readouterr().out
    assert "updated" in out
    assert "Update complete." in out


def test_tui_escape_hatch(monkeypatch) -> None:
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)
    assert tui_style.tui_escape_allowed() is False
    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "1")
    assert tui_style.tui_escape_allowed() is True


def test_exit_stays_in_console(monkeypatch, capsys) -> None:
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)
    calls = {"n": 0}

    def fake_input(_prompt: str = "") -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "/exit"
        raise RuntimeError("still-in-loop")

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(main_console, "_print_banner", lambda: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    monkeypatch.setattr(tui_style, "install_terminal_guard", lambda: None)
    with pytest.raises(RuntimeError, match="still-in-loop"):
        main_console.run_main_console()
    assert "There is no outside" in capsys.readouterr().out


def test_exit_leaves_when_hatch_open(monkeypatch) -> None:
    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "1")
    monkeypatch.setattr("builtins.input", lambda _prompt="": "/exit")
    monkeypatch.setattr(main_console, "_print_banner", lambda: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    monkeypatch.setattr(tui_style, "install_terminal_guard", lambda: None)
    main_console.run_main_console()


def test_pin_to_tui_ignores_sigtstp() -> None:
    import signal

    previous = signal.getsignal(signal.SIGTSTP)
    try:
        tui_style.pin_to_tui()
        assert signal.getsignal(signal.SIGTSTP) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGTSTP, previous)


def test_thinking_sparkles_stop_is_safe() -> None:
    spark = tui_style.thinking_sparkles(width=20)
    spark.__enter__()
    spark.stop()
    spark.stop()


def test_eof_on_dead_stdin_exits_without_desktop_spawn(monkeypatch) -> None:
    class _DeadStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(main_console.sys, "stdin", _DeadStdin())
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(EOFError()))
    monkeypatch.setattr(main_console, "_print_banner", lambda: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    monkeypatch.setattr(tui_style, "install_terminal_guard", lambda: None)

    spawned: list[list[str]] = []

    def fake_popen(cmd, **_kwargs):
        spawned.append(list(cmd))
        raise AssertionError("should not spawn")

    monkeypatch.setattr(main_console.subprocess, "Popen", fake_popen)
    main_console.run_main_console()
    assert spawned == []
