import pytest
from pathlib import Path

from hosaka import main_console
from hosaka.tui import style as tui_style


@pytest.mark.parametrize("command", ["/paths", "/paths --json"])
def test_tui_paths_uses_shared_dispatch(command, tmp_path, monkeypatch):
    from hosaka import paths

    calls = []
    monkeypatch.setattr(paths, "main", lambda args: calls.append(args) or 0)
    assert main_console._dispatch_command(command, tmp_path, "llm") == (tmp_path, "llm")
    assert calls == [command.split()[1:]]


def test_tui_offline_doctor_uses_shared_dispatch(tmp_path, monkeypatch):
    from hosaka import doctor

    calls = []
    monkeypatch.setattr(doctor, "main", lambda args: calls.append(args) or 0)
    main_console._dispatch_command("/doctor --offline", tmp_path, "llm")
    assert calls == [["--offline"]]


@pytest.mark.parametrize("command", ["/migrate --dry-run", "/migrate --dry-run --json", "/migrate --json --dry-run"])
def test_tui_migration_uses_shared_dispatch(command, tmp_path, monkeypatch):
    from hosaka import migration

    calls = []
    monkeypatch.setattr(migration, "main", lambda args: calls.append(args) or 0)
    assert main_console._dispatch_command(command, tmp_path, "llm") == (tmp_path, "llm")
    assert calls == [command.split()[1:]]


@pytest.mark.parametrize("command", ["/extensions list --json", "/extensions create demo-package", "/extensions"])
def test_tui_extensions_uses_shared_dispatch(command, tmp_path, monkeypatch):
    from hosaka.extensions import __main__ as extensions

    calls = []
    monkeypatch.setattr(extensions, "main", lambda args: calls.append(args) or 0)
    assert main_console._dispatch_command(command, tmp_path, "llm") == (tmp_path, "llm")
    assert calls == [command.split()[1:]]


def test_tui_extensions_invalid_command_does_not_exit_console(tmp_path, capsys):
    assert main_console._dispatch_command("/extensions run missing", tmp_path, "llm") == (tmp_path, "llm")
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["/migrate", "/migrate --apply", "/migrate --dry-run --unknown"])
def test_tui_migration_invalid_arguments_do_not_exit_console(command, tmp_path, monkeypatch, capsys):
    from hosaka import migration

    monkeypatch.setattr(migration, "main", lambda args: pytest.fail("Invalid inventory dispatched"))
    assert main_console._dispatch_command(command, tmp_path, "llm") == (tmp_path, "llm")
    assert "Usage: /migrate --dry-run" in capsys.readouterr().out


def test_first_run_saves_hidden_key_without_mutating_picoclaw(tmp_path, monkeypatch, capsys):
    import json
    from hosaka.llm import llm_config, openai_adapter, picoclaw_adapter
    from hosaka.secrets import store

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"version": 3, "model_list": []}))
    original = config_path.read_bytes()
    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: True)
    monkeypatch.setattr(openai_adapter, "_picoclaw_config_path", lambda: config_path)
    monkeypatch.setattr(openai_adapter, "resolve_api_key", lambda: (None, None))
    prompts = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: prompts.append(prompt) or "test-secret")
    saved_secrets = []
    monkeypatch.setattr(store, "set", lambda *args, **kwargs: saved_secrets.append((args, kwargs)))
    monkeypatch.setattr(llm_config, "load", lambda: {"profiles": {"ollama": {"model": "local"}}})
    saved_configs = []
    monkeypatch.setattr(llm_config, "save", saved_configs.append)
    applied = []
    monkeypatch.setattr(llm_config, "apply_to_env", applied.append)
    main_console._check_api_key()
    assert prompts and "hidden" in prompts[0]
    assert saved_secrets == [(("OPENAI_API_KEY", "test-secret"), {"mirror": False})]
    assert saved_configs[0]["provider"] == "openai"
    assert saved_configs[0]["profiles"]["ollama"]["model"] == "local"
    assert applied == saved_configs
    assert config_path.read_bytes() == original
    assert "test-secret" not in capsys.readouterr().out


def test_first_run_initializes_missing_picoclaw_config(tmp_path, monkeypatch):
    import subprocess
    from hosaka.llm import openai_adapter, picoclaw_adapter

    config_path = tmp_path / "custom/config.json"
    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: True)
    monkeypatch.setattr(openai_adapter, "_picoclaw_config_path", lambda: config_path)
    monkeypatch.setattr(openai_adapter, "resolve_api_key", lambda: ("existing", "env"))
    calls = []

    def onboard(command, **kwargs):
        calls.append((command, kwargs))
        config_path.parent.mkdir()
        config_path.write_text("{}")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(main_console.subprocess, "run", onboard)
    monkeypatch.setattr("getpass.getpass", lambda *a: pytest.fail("Existing credential was ignored"))
    main_console._check_api_key()
    assert calls[0][0][-1] == "onboard"
    assert calls[0][1]["env"]["PICOCLAW_HOME"] == str(config_path.parent)


def test_first_run_reports_missing_binary_without_prompt(monkeypatch, capsys):
    from hosaka.llm import picoclaw_adapter

    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: False)
    monkeypatch.setattr("getpass.getpass", lambda *a: pytest.fail("Cannot use an uninstalled agent"))
    main_console._check_api_key()
    assert "install-picoclaw.sh --onboard" in capsys.readouterr().out


def test_first_run_reports_failed_onboarding(tmp_path, monkeypatch, capsys):
    import subprocess
    from hosaka.llm import openai_adapter, picoclaw_adapter

    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: True)
    monkeypatch.setattr(openai_adapter, "_picoclaw_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(main_console.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "cannot write config"))
    main_console._check_api_key()
    assert "PicoClaw setup failed" in capsys.readouterr().out


def test_first_run_skip_does_not_write_credentials(tmp_path, monkeypatch, capsys):
    from hosaka.llm import openai_adapter, picoclaw_adapter
    from hosaka.secrets import store

    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: True)
    monkeypatch.setattr(openai_adapter, "_picoclaw_config_path", lambda: config_path)
    monkeypatch.setattr(openai_adapter, "resolve_api_key", lambda: (None, None))
    monkeypatch.setattr("getpass.getpass", lambda *a: "")
    monkeypatch.setattr(store, "set", lambda *a, **k: pytest.fail("Skipped key was saved"))
    main_console._check_api_key()
    assert "Skipped" in capsys.readouterr().out


@pytest.mark.parametrize("text", ["busted", "hands up", "\U0001f600" * 80])
def test_flash_emits_gui_event_without_dispatching_chat(monkeypatch, capsys, tmp_path, text) -> None:
    import json

    monkeypatch.setenv("HOSAKA_TERMINAL_GUI", "1")
    result = main_console._dispatch_command(f"/flash {text}", tmp_path, "llm")
    assert result == (tmp_path, "llm")
    output = capsys.readouterr().out
    assert output == f"\033]777;hosaka-flash;{json.dumps(text.upper())}\007"


@pytest.mark.parametrize("command", ["/flash", "/flash ", "/flash    "])
def test_flash_defaults_to_busted(monkeypatch, capsys, tmp_path, command) -> None:
    monkeypatch.setenv("HOSAKA_TERMINAL_GUI", "1")
    result = main_console._dispatch_command(command, tmp_path, "llm")
    assert result == (tmp_path, "llm")
    assert capsys.readouterr().out == '\033]777;hosaka-flash;"BUSTED"\007'


def test_flash_custom_text_overrides_default(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("HOSAKA_TERMINAL_GUI", "1")
    main_console._dispatch_command("/flash", tmp_path, "llm")
    assert capsys.readouterr().out == '\033]777;hosaka-flash;"BUSTED"\007'
    main_console._dispatch_command("/flash hands up", tmp_path, "llm")
    assert capsys.readouterr().out == '\033]777;hosaka-flash;"HANDS UP"\007'


@pytest.mark.parametrize("text", ["x" * 81, "word\007word"])
def test_flash_rejects_invalid_text(monkeypatch, capsys, tmp_path, text) -> None:
    monkeypatch.setenv("HOSAKA_TERMINAL_GUI", "1")
    main_console._dispatch_command(f"/flash {text}", tmp_path, "llm")
    output = capsys.readouterr().out
    assert "Usage: /flash" in output
    assert "\033]777" not in output


@pytest.mark.parametrize("command", ["/flash", "/flash busted"])
def test_flash_requires_gui(monkeypatch, capsys, tmp_path, command) -> None:
    monkeypatch.delenv("HOSAKA_TERMINAL_GUI", raising=False)
    main_console._dispatch_command(command, tmp_path, "llm")
    assert "requires the terminal-first GUI" in capsys.readouterr().out


def test_tui_start_restores_saved_llm_over_inherited_environment(monkeypatch, tmp_path) -> None:
    from hosaka.llm import llm_config, openai_adapter

    monkeypatch.setenv("HOSAKA_STATE_PATH", str(tmp_path / "state.json"))
    llm_config.save({
        "provider": "openai", "model": "gpt-4.1",
        "base_url": "https://api.openai.com", "api_key": "saved-test-key",
    })
    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "1")
    monkeypatch.setattr(main_console, "_print_banner", lambda: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    monkeypatch.setattr(tui_style, "install_terminal_guard", lambda: None)

    for _ in range(2):
        monkeypatch.setenv("OPENAI_MODEL", "qwen2.5:0.5b")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "ollama")

        def input_(_prompt):
            assert openai_adapter._model() == "gpt-4.1"
            assert openai_adapter._chat_url() == "https://api.openai.com/v1/chat/completions"
            assert openai_adapter.resolve_api_key()[0] == "saved-test-key"
            return "/exit"

        monkeypatch.setattr("builtins.input", input_)
        main_console.run_main_console()


def test_unconfigured_llm_defaults_to_gpt41(monkeypatch, tmp_path) -> None:
    from hosaka.llm import llm_config

    monkeypatch.setenv("HOSAKA_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.delenv("HOSAKA_LOCAL_FIRST", raising=False)
    assert llm_config.load() == {
        "provider": "openai", "model": "gpt-4.1", "base_url": "https://api.openai.com",
    }


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
    assert "Update request accepted." in out


def test_tui_escape_hatch(monkeypatch) -> None:
    monkeypatch.setattr(tui_style.sys, "platform", "linux")
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)
    assert tui_style.tui_escape_allowed() is False
    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "1")
    assert tui_style.tui_escape_allowed() is True


def test_exit_stays_in_console(monkeypatch, capsys) -> None:
    monkeypatch.setattr(tui_style.sys, "platform", "linux")
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


def test_pin_to_tui_ignores_sigtstp(monkeypatch) -> None:
    import signal

    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "0")
    previous = signal.getsignal(signal.SIGTSTP)
    try:
        tui_style.pin_to_tui()
        assert signal.getsignal(signal.SIGTSTP) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGTSTP, previous)


def test_macos_escape_default_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setattr(tui_style.sys, "platform", "darwin")
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)
    assert tui_style.tui_escape_allowed() is True
    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "0")
    assert tui_style.tui_escape_allowed() is False


def test_pin_to_tui_preserves_job_control_with_escape_enabled(monkeypatch) -> None:
    import signal

    monkeypatch.setenv("HOSAKA_ALLOW_SHELL", "1")
    with pytest.MonkeyPatch.context() as signals:
        calls = []
        signals.setattr(signal, "signal", lambda *args: calls.append(args))
        tui_style.pin_to_tui()
    assert calls == []


@pytest.mark.parametrize("control", [EOFError, KeyboardInterrupt, "/exit"])
def test_macos_prompt_can_exit(monkeypatch, control) -> None:
    monkeypatch.setattr(tui_style.sys, "platform", "darwin")
    monkeypatch.delenv("HOSAKA_ALLOW_SHELL", raising=False)

    def fake_input(_prompt=""):
        if isinstance(control, str):
            return control
        raise control()

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(main_console, "_print_banner", lambda: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    monkeypatch.setattr(tui_style, "install_terminal_guard", lambda: None)
    monkeypatch.setattr(main_console, "_drop_to_desktop", lambda: pytest.fail("desktop"))
    main_console.run_main_console()


def test_shell_command_prefix_bypasses_llm(monkeypatch, tmp_path) -> None:
    commands = []
    monkeypatch.setattr(
        main_console, "_run_shell_command", lambda command, cwd: commands.append((command, cwd))
    )
    monkeypatch.setattr(main_console, "one_shot", lambda *a, **k: pytest.fail("called AI"))
    assert main_console._dispatch_command(
        "!networksetup -getairportpower en0", tmp_path, "llm"
    ) == (tmp_path, "llm")
    assert commands == [("networksetup -getairportpower en0", tmp_path)]


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
    assert "/select llm" in out
    assert "play a game" in out
    assert "/gui" not in out
    assert all(command != "/gui" for command, _desc, _cat in main_console.COMMANDS)


def test_select_llm_dispatch_bypasses_chat(monkeypatch, tmp_path) -> None:
    from hosaka import llm_cli

    calls = []
    monkeypatch.setattr(llm_cli, "select_llm", lambda argument: calls.append(argument))
    monkeypatch.setattr(main_console, "one_shot", lambda *a, **k: pytest.fail("called AI"))
    for command in ("/select llm", "/select llm 0"):
        assert main_console._dispatch_command(command, tmp_path, "llm") == (tmp_path, "llm")
    assert calls == ["", "0"]


def test_foliate_manifest_opens_shelf_without_books_directory() -> None:
    manifest = (
        Path(main_console.APP_ROOT) / "hosaka-apps" / "apps" / "foliate.yaml"
    ).read_text(encoding="utf-8")
    launch = manifest.split("launch:", 1)[1].split("aliases:", 1)[0]

    assert "com.github.johnfactotum.Foliate" in launch
    assert "\n    - $HOME/Books" not in launch
