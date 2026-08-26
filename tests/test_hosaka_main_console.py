import pytest
from pathlib import Path

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


def test_read_portal_books_launches_foliate(monkeypatch) -> None:
    launched: list[bool] = []
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    monkeypatch.setattr(main_console, "_launch_foliate", lambda: launched.append(True))

    main_console._show_read_portal()

    assert launched == [True]


def test_read_portal_field_history_opens_library(monkeypatch) -> None:
    opened: list[bool] = []
    monkeypatch.setattr("builtins.input", lambda _prompt="": "2")
    monkeypatch.setattr(main_console, "_show_library", lambda: opened.append(True))

    main_console._show_read_portal()

    assert opened == [True]


def test_launch_foliate_uses_hosaka_app_launcher(monkeypatch) -> None:
    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(main_console.shutil, "which", lambda _name: "/usr/bin/hosaka")

    def fake_popen(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return object()

    monkeypatch.setattr(main_console.subprocess, "Popen", fake_popen)
    main_console._launch_foliate()

    assert calls[0][0] == ["/usr/bin/hosaka", "launch", "foliate"]
    assert calls[0][1]["start_new_session"] is True


def test_read_aliases_and_slug_dispatch(monkeypatch) -> None:
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_console, "_launch_foliate", lambda: events.append(("launch", "foliate"))
    )
    monkeypatch.setattr(
        main_console, "_show_library", lambda: events.append(("show", "history"))
    )
    monkeypatch.setattr(
        main_console,
        "_read_file",
        lambda argument, current_dir: events.append(("read", argument)),
    )

    for command in ("/read books", "/read history", "/read the-field-terminal"):
        main_console._dispatch_command(command, main_console.APP_ROOT, "llm")

    assert events == [
        ("launch", "foliate"),
        ("show", "history"),
        ("read", "the-field-terminal"),
    ]


def test_help_is_discovery_map_without_gui(capsys) -> None:
    main_console._show_help()
    out = capsys.readouterr().out

    assert "/read the-field-terminal" in out
    assert "/plant  /orb" in out
    assert "play a game" in out
    assert "/gui" not in out
    assert all(command != "/gui" for command, _desc, _cat in main_console.COMMANDS)


def test_foliate_manifest_opens_shelf_without_books_directory() -> None:
    manifest = (
        Path(main_console.APP_ROOT) / "hosaka-apps" / "apps" / "foliate.yaml"
    ).read_text(encoding="utf-8")
    launch = manifest.split("launch:", 1)[1].split("aliases:", 1)[0]

    assert "com.github.johnfactotum.Foliate" in launch
    assert "\n    - $HOME/Books" not in launch
