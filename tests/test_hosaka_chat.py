"""Tests for the LLM router, chat module, and adapters."""

from __future__ import annotations

import json
import signal
import time
import pytest
from unittest.mock import patch, MagicMock
import hosaka.llm.router as router_mod
from hosaka.llm.router import LLMBackend, detect_backend, sync_chat


class TestDetectBackend:
    def test_picoclaw_preferred(self) -> None:
        with patch("hosaka.llm.picoclaw_adapter.is_available", return_value=True):
            assert detect_backend() == LLMBackend.PICOCLAW

    def test_openai_fallback(self) -> None:
        with (
            patch("hosaka.llm.picoclaw_adapter.is_available", return_value=False),
            patch("hosaka.llm.openai_adapter.is_available", return_value=True),
        ):
            assert detect_backend() == LLMBackend.OPENAI

    def test_offline_last_resort(self) -> None:
        with (
            patch("hosaka.llm.picoclaw_adapter.is_available", return_value=False),
            patch("hosaka.llm.openai_adapter.is_available", return_value=False),
        ):
            assert detect_backend() == LLMBackend.OFFLINE


def test_llm_config_saved_atomically_with_private_permissions(tmp_path, monkeypatch):
    from hosaka.llm import llm_config

    path = tmp_path / "llm.json"
    path.write_text('{"old": true}')
    path.chmod(0o644)
    monkeypatch.setattr(llm_config, "_config_file", lambda: path)
    llm_config.save({"api_key": "private"})
    assert json.loads(path.read_text()) == {"api_key": "private"}
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_llm_config_failed_replace_keeps_old_settings(tmp_path, monkeypatch):
    from hosaka.llm import llm_config

    path = tmp_path / "llm.json"
    path.write_text('{"model": "old"}')
    monkeypatch.setattr(llm_config, "_config_file", lambda: path)

    def failed_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(llm_config.os, "replace", failed_replace)
    with pytest.raises(OSError, match="disk unavailable"):
        llm_config.save({"model": "new"})
    assert json.loads(path.read_text()) == {"model": "old"}
    assert list(tmp_path.iterdir()) == [path]


def test_root_llm_save_keeps_shared_settings_operator_owned(tmp_path, monkeypatch):
    from hosaka.llm import llm_config
    import os

    path = tmp_path / "llm.json"
    monkeypatch.setattr(llm_config, "_config_file", lambda: path)
    monkeypatch.setattr(llm_config.os, "geteuid", lambda: 0)
    owners = []
    monkeypatch.setattr(llm_config.os, "fchown", lambda fd, uid, gid: owners.append((uid, gid)))
    llm_config.save({"model": "gpt-4.1"})
    assert owners == [(os.stat(tmp_path).st_uid, os.stat(tmp_path).st_gid)]
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("command,response,expected", [
    ("message", "ok", 0), ("message", "", 1), ("chat", "ok", 0),
])
def test_cli_chat_uses_console_provider_and_session(monkeypatch, command, response, expected):
    from hosaka.llm import chat, llm_config
    from hosaka import main_console

    applied = []
    config = {"provider": "openai", "model": "gpt-4.1"}
    monkeypatch.setattr(llm_config, "load", lambda: config)
    monkeypatch.setattr(llm_config, "apply_to_env", applied.append)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    calls = []
    monkeypatch.setattr(chat, "_print_stream", lambda *a, **k: calls.append((a, k)) or response)
    assert chat.main([command, "--session", "test-session", "hello"]) == expected
    assert applied == [config]
    assert calls[0][1]["backend"] == LLMBackend.PICOCLAW
    assert calls[0][1]["session"] == "test-session"
    assert calls[0][0][0][-1] == {"role": "user", "content": "hello"}


def test_cli_interactive_chat_keeps_explicit_session(monkeypatch):
    from hosaka.llm import chat, llm_config
    from hosaka import main_console

    monkeypatch.setattr(llm_config, "load", lambda: {})
    monkeypatch.setattr(llm_config, "apply_to_env", lambda cfg: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    calls = []
    monkeypatch.setattr(chat, "enter_chat_mode", lambda *a, **k: calls.append((a, k)))
    assert chat.main(["chat", "--session", "custom"]) == 0
    assert calls[0][1]["session"] == "custom"


def test_cli_chat_preserves_native_one_shot_option(monkeypatch):
    from hosaka.llm import chat, llm_config
    from hosaka import main_console

    monkeypatch.setattr(llm_config, "load", lambda: {})
    monkeypatch.setattr(llm_config, "apply_to_env", lambda cfg: None)
    monkeypatch.setattr(main_console, "_check_api_key", lambda: None)
    calls = []
    monkeypatch.setattr(chat, "_print_stream", lambda *a, **k: calls.append((a, k)) or "ok")
    assert chat.main(["chat", "-m", "hello"]) == 0
    assert calls[0][0][0][-1]["content"] == "hello"

class TestSyncChat:
    def test_picoclaw_used_when_available(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        with patch("hosaka.llm.picoclaw_adapter.chat_sync", return_value="pico response") as mock_sync:
            result = sync_chat(messages, backend=LLMBackend.PICOCLAW)
        assert result == "pico response"
        mock_sync.assert_called_once_with("hello", session=None)

    def test_picoclaw_error_text_falls_back_to_openai(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        with (
            patch(
                "hosaka.llm.picoclaw_adapter.chat_sync",
                side_effect=RuntimeError("llm call failed after retries"),
            ),
            patch("hosaka.llm.openai_adapter.is_available", return_value=True),
            patch("hosaka.llm.openai_adapter.chat_sync", return_value="openai response"),
        ):
            result = sync_chat(messages, backend=LLMBackend.PICOCLAW)
        assert result == "openai response"

    def test_offline_fallback_uses_intent(self) -> None:
        messages = [{"role": "user", "content": "help me get on wifi"}]
        with (
            patch("hosaka.llm.picoclaw_adapter.is_available", return_value=False),
            patch("hosaka.llm.openai_adapter.is_available", return_value=False),
        ):
            result = sync_chat(messages, backend=LLMBackend.OFFLINE)
        assert "[offline]" in result
        assert "Network" in result or "network" in result.lower()

    def test_offline_general_fallback(self) -> None:
        messages = [{"role": "user", "content": "random unknown thing"}]
        result = sync_chat(messages, backend=LLMBackend.OFFLINE)
        assert "[offline]" in result


def test_stream_failure_is_reported_before_offline_fallback() -> None:
    with (
        patch("hosaka.llm.openai_adapter.is_available", return_value=True),
        patch("hosaka.llm.openai_adapter.chat_stream", side_effect=RuntimeError("unreachable")),
    ):
        result = "".join(router_mod.stream_chat(
            [{"role": "user", "content": "hello"}], backend=LLMBackend.OPENAI
        ))
    assert "LLM connection failed: unreachable" in result
    assert "[offline]" in result


def test_conversational_backend_requires_picoclaw() -> None:
    from hosaka.llm import chat as chat_mod

    with (
        patch.object(chat_mod.openai_adapter, "is_available", return_value=True),
        patch.object(chat_mod.picoclaw_adapter, "is_available", return_value=True),
    ):
        assert chat_mod._conversational_backend() == LLMBackend.PICOCLAW


def test_console_chat_uses_native_harness_not_direct_tools(monkeypatch, capsys) -> None:
    from hosaka.llm import chat

    with (
        patch.object(chat.picoclaw_adapter, "console_chat_stream", return_value=(t for t in ["native reply"])) as agent,
        patch.object(chat, "stream_chat") as direct,
    ):
        chat.one_shot("inspect this machine", hostname="test-host", cwd="/tmp")
    direct.assert_not_called()
    assert agent.call_args.kwargs["cwd"] == "/tmp"
    assert agent.call_args.kwargs["session"] == "hosaka:tui"
    context = agent.call_args.args[0][0]["content"]
    assert "Operating system:" in context
    assert "test-host" in context
    assert "native file, shell/exec" in context
    assert "native reply" in capsys.readouterr().out


def test_console_agent_failure_never_falls_back(capsys) -> None:
    from hosaka.llm import chat

    with (
        patch.object(chat.picoclaw_adapter, "console_chat_stream", side_effect=RuntimeError("agent unavailable")),
        patch.object(chat, "stream_chat") as direct,
    ):
        chat.one_shot("hello", hostname="test", cwd="/tmp")
    direct.assert_not_called()
    output = capsys.readouterr().out
    assert "agent unavailable" in output
    assert "No direct LLM fallback" in output


@pytest.mark.parametrize("explicit_model", [None, "my-local-model"])
@pytest.mark.parametrize("native_search", [None, True, False])
def test_console_picoclaw_overlay_preserves_tools_sessions_and_config(
    tmp_path, monkeypatch, explicit_model, native_search,
) -> None:
    from hosaka.llm import openai_adapter, picoclaw_adapter

    workspace = tmp_path / "workspace"
    config_path = tmp_path / "config.json"
    config = {
        "version": 3,
        "agents": {"defaults": {"workspace": str(workspace), "restrict_to_workspace": True}},
        "model_list": [{"model_name": "original", "model": "ollama/test"}],
        "tools": {"exec": {"enabled": True}},
    }
    if native_search is not None:
        config["tools"]["web"] = {"prefer_native": native_search, "provider": "duckduckgo"}
    config_path.write_text(json.dumps(config))
    original = config_path.read_bytes()
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: True)
    monkeypatch.setattr(openai_adapter, "_api_key", lambda: "test-secret")
    monkeypatch.setattr(openai_adapter, "_model", lambda: "gpt-4.1")
    monkeypatch.setattr(openai_adapter, "_api_base_url", lambda: "https://api.openai.com/v1")
    monkeypatch.delenv("PICOCLAW_MODEL", raising=False)
    if explicit_model:
        monkeypatch.setenv("PICOCLAW_MODEL", explicit_model)
    runtime_paths = []

    def fake_chat(message, session, timeout, *, cwd, env, model):
        from pathlib import Path
        runtime = Path(env["PICOCLAW_HOME"])
        runtime_paths.append(runtime)
        overlay = json.loads((runtime / "config.json").read_text())
        expected_tools = {**config["tools"], "web": {**config["tools"].get("web", {}), "prefer_native": False}}
        assert overlay["tools"] == expected_tools
        assert overlay["agents"] == config["agents"]
        assert (runtime / "config.json").stat().st_mode & 0o777 == 0o600
        assert model == (explicit_model or "hosaka-console")
        if not explicit_model:
            assert overlay["model_list"] == [{
                "model_name": "hosaka-console", "model": "openai/gpt-4.1",
                "api_base": "https://api.openai.com/v1",
            }]
            assert "hosaka-console:0:" in (runtime / ".security.yml").read_text()
            assert '"test-secret"' in (runtime / ".security.yml").read_text()
        assert session == picoclaw_adapter._console_session_key("hosaka:tui")
        assert cwd == "/tmp"
        assert "Darwin" in message
        assert "Operator request:\nhello" in message
        return "agent reply"

    monkeypatch.setattr(picoclaw_adapter, "chat_sync", fake_chat)
    assert "".join(picoclaw_adapter.console_chat_stream(
        [{"role": "system", "content": "OS: Darwin"}, {"role": "user", "content": "hello"}],
        cwd="/tmp",
    )) == "agent reply"
    assert config_path.read_bytes() == original
    assert runtime_paths and not runtime_paths[0].exists()


def test_real_picoclaw_sends_selected_credentials_with_duplicate_model_alias(tmp_path, monkeypatch):
    import shutil
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from hosaka.llm import openai_adapter, picoclaw_adapter

    if not shutil.which(picoclaw_adapter.PICOCLAW_BIN):
        pytest.skip("PicoClaw binary required; release CI installs it")
    captured = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            authorized = self.headers.get("Authorization") == "Bearer test-runtime-key"
            captured.append((authorized, payload))
            response = {
                "id": "local-test", "object": "chat.completion", "created": 0,
                "model": "gpt-4.1",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "LOCAL_OK"},
                             "finish_reason": "stop"}],
            } if authorized else {"error": {"message": "Missing selected credential"}}
            body = json.dumps(response).encode()
            self.send_response(200 if authorized else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/v1"
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "version": 3,
        "agents": {"defaults": {"workspace": str(tmp_path / "workspace"), "model_name": "gpt-4.1"}},
        "model_list": [{"model_name": "gpt-4.1", "model": "openai/gpt-4.1", "api_base": base}],
        "tools": {"web": {"prefer_native": True}},
    }))
    original = config_path.read_bytes()
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("PICOCLAW_SECURITY_PATH", raising=False)
    monkeypatch.delenv("PICOCLAW_MODEL", raising=False)
    monkeypatch.setattr(openai_adapter, "_api_key", lambda: "test-runtime-key")
    monkeypatch.setattr(openai_adapter, "_model", lambda: "gpt-4.1")
    monkeypatch.setattr(openai_adapter, "_api_base_url", lambda: base)
    try:
        response = "".join(picoclaw_adapter.console_chat_stream(
            [{"role": "user", "content": "Reply LOCAL_OK. Do not use tools."}], timeout=20,
        ))
        assert response == "LOCAL_OK"
        assert captured and all(authorized for authorized, _ in captured)
        assert all(payload["model"] == "gpt-4.1" for _, payload in captured)
        assert all(
            tool["type"] in {"function", "custom"}
            for _, payload in captured for tool in payload.get("tools", [])
        )
        assert config_path.read_bytes() == original
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_picoclaw_nonzero_exit_is_not_success(monkeypatch) -> None:
    import subprocess
    from hosaka.llm import picoclaw_adapter

    monkeypatch.setattr(picoclaw_adapter.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 1, stdout="banner", stderr="provider unavailable",
    ))
    with pytest.raises(RuntimeError, match="provider unavailable"):
        picoclaw_adapter.chat_sync("hello")


def test_console_workspace_override(tmp_path, monkeypatch) -> None:
    from hosaka.llm import picoclaw_adapter

    project = tmp_path / "project"
    project.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "agents": {"defaults": {"workspace": "/original", "restrict_to_workspace": True}},
        "model_list": [{"model_name": "profile", "model": "anthropic/example"}],
    }))
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("PICOCLAW_MODEL", "profile")
    monkeypatch.setenv("HOSAKA_WORKSPACE", str(project))
    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: True)

    def inspect_overlay(*args, **kwargs):
        from pathlib import Path
        overlay = json.loads((Path(kwargs["env"]["PICOCLAW_HOME"]) / "config.json").read_text())
        assert overlay["agents"]["defaults"]["workspace"] == str(project)
        assert overlay["agents"]["defaults"]["restrict_to_workspace"] is True
        return "ok"

    monkeypatch.setattr(picoclaw_adapter, "chat_sync", inspect_overlay)
    assert "".join(picoclaw_adapter.console_chat_stream([{"role": "user", "content": "hello"}])) == "ok"
    assert json.loads(config_path.read_text())["agents"]["defaults"]["workspace"] == "/original"
    monkeypatch.setenv("HOSAKA_WORKSPACE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="workspace does not exist"):
        list(picoclaw_adapter.console_chat_stream([{"role": "user", "content": "hello"}]))


def test_picoclaw_empty_response_is_not_banner_success(monkeypatch) -> None:
    import subprocess
    from hosaka.llm import picoclaw_adapter

    monkeypatch.setattr(picoclaw_adapter.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, stdout="🦞 picoclaw 0.2.8\n╚══════╝", stderr="",
    ))
    with pytest.raises(RuntimeError, match="empty response"):
        picoclaw_adapter.chat_sync("hello")


def test_picoclaw_response_preserves_workspace_paths_and_mentions() -> None:
    from hosaka.llm import picoclaw_adapter

    raw = (
        "🦞 picoclaw 0.2.8\n"
        "18:00:33 WRN agent > diagnostic\n"
        "🦞 PicoClaw can use exec.\n"
        "pwd: /Users/test/.picoclaw/workspace\n"
    )
    assert picoclaw_adapter._extract_response(raw) == (
        "PicoClaw can use exec.\npwd: /Users/test/.picoclaw/workspace"
    )


def test_console_harness_requires_installed_binary(monkeypatch) -> None:
    from hosaka.llm import picoclaw_adapter

    monkeypatch.setattr(picoclaw_adapter, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="not installed"):
        list(picoclaw_adapter.console_chat_stream([{"role": "user", "content": "hello"}]))


def test_console_session_keys_are_stable_and_isolated() -> None:
    from hosaka.llm.picoclaw_adapter import _console_session_key

    key = _console_session_key("hosaka:tui")
    assert key.startswith("sk_v1_")
    assert key == _console_session_key("HOSAKA:TUI")
    assert key != _console_session_key("hosaka:voice")
    assert _console_session_key(key) == key


def test_chat_clear_starts_a_fresh_native_session(monkeypatch, capsys) -> None:
    from hosaka.llm import chat

    inputs = iter(["first", "/clear", "/session", "second", "/back"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    with patch.object(chat, "_print_stream", return_value="reply") as stream:
        chat.enter_chat_mode(hostname="host", cwd="/tmp")
    assert stream.call_args_list[0].kwargs["session"] == "hosaka:tui"
    new_session = stream.call_args_list[1].kwargs["session"]
    assert new_session.startswith("hosaka:tui:")
    assert f"Session: {new_session}" in capsys.readouterr().out
    assert [msg["content"] for msg in stream.call_args_list[1].args[0] if msg["role"] == "user"] == ["second"]


def test_console_chat_has_total_deadline(monkeypatch, capsys) -> None:
    from hosaka.llm import chat, openai_adapter

    def slow_complete(*args, **kwargs):
        time.sleep(0.3)
        return {"role": "assistant", "content": "too late"}

    monkeypatch.setattr(openai_adapter, "REQUEST_TIMEOUT", 0.05)
    monkeypatch.setattr(openai_adapter, "_api_key", lambda: "test")
    monkeypatch.setattr(openai_adapter, "_complete", slow_complete)
    with patch("hosaka.tui.style.thinking_sparkles") as spark:
        started = time.monotonic()
        result = chat._print_stream(
            [{"role": "user", "content": "hello"}], backend=LLMBackend.OPENAI
        )
        elapsed = time.monotonic() - started
    assert result == ""
    assert elapsed < 0.25
    assert "timed out" in capsys.readouterr().out
    spark.return_value.stop.assert_called()


def test_console_chat_interrupt_closes_stream(monkeypatch, capsys) -> None:
    from hosaka.llm import chat

    closed = []

    def interrupted(*args, **kwargs):
        try:
            yield "partial"
            raise KeyboardInterrupt
        finally:
            closed.append(True)

    monkeypatch.setattr(chat, "stream_chat", interrupted)
    assert chat._print_stream([]) == ""
    assert closed == [True]
    assert "cancelled" in capsys.readouterr().out


def test_console_chat_deadline_covers_continuous_tokens(monkeypatch, capsys) -> None:
    from hosaka.llm import chat, openai_adapter

    closed = []
    previous_handler = signal.getsignal(signal.SIGALRM)

    def trickling(*args, **kwargs):
        try:
            for _ in range(30):
                time.sleep(0.01)
                yield "."
        finally:
            closed.append(True)

    monkeypatch.setattr(openai_adapter, "REQUEST_TIMEOUT", 0.05)
    monkeypatch.setattr(chat, "stream_chat", trickling)
    assert chat._print_stream([]) == ""
    assert closed == [True]
    assert "timed out" in capsys.readouterr().out
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == previous_handler

    monkeypatch.setattr(chat, "stream_chat", lambda *a, **k: (t for t in ["hello", " there"]))
    assert chat._print_stream([]) == "hello there"


def test_console_chat_deadline_interrupts_trickling_http_body(monkeypatch, capsys) -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from hosaka.llm import chat, openai_adapter

    stop = threading.Event()
    finished = threading.Event()

    class SlowResponse(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            try:
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Length", "50")
                self.end_headers()
                for _ in range(50):
                    if stop.wait(0.01):
                        break
                    self.wfile.write(b" ")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                finished.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowResponse)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    monkeypatch.setattr(openai_adapter, "_api_key", lambda: "test")
    monkeypatch.setattr(openai_adapter, "_model", lambda: "test")
    monkeypatch.setattr(openai_adapter, "_assert_chat_backend", lambda: None)
    monkeypatch.setattr(
        openai_adapter, "_chat_url", lambda: f"http://127.0.0.1:{server.server_port}/chat"
    )
    monkeypatch.setattr(openai_adapter, "REQUEST_TIMEOUT", 0.15)
    try:
        started = time.monotonic()
        assert chat._print_stream([], backend=LLMBackend.OPENAI) == ""
        assert time.monotonic() - started < 0.4
        assert "timed out" in capsys.readouterr().out
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
    assert finished.wait(1)
    assert not thread.is_alive()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_console_chat_rejects_invalid_deadline(timeout) -> None:
    from hosaka.llm.chat import _chat_deadline

    with pytest.raises(ValueError, match="finite positive"):
        with _chat_deadline(timeout):
            pytest.fail("invalid deadline was accepted")


def test_console_chat_reports_empty_response(monkeypatch, capsys) -> None:
    from hosaka.llm import chat

    monkeypatch.setattr(chat, "stream_chat", lambda *a, **k: (t for t in []))
    assert chat._print_stream([]) == ""
    assert "no response" in capsys.readouterr().out


def test_console_chat_deadline_kills_waiting_subprocess(monkeypatch, capsys) -> None:
    import subprocess
    import sys
    from hosaka.llm import chat, openai_adapter

    children = []
    real_popen = subprocess.Popen

    def tracked_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    def waiting(*args, **kwargs):
        subprocess.run(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            capture_output=True,
            check=True,
        )
        yield "too late"

    monkeypatch.setattr(subprocess, "Popen", tracked_popen)
    monkeypatch.setattr(chat, "stream_chat", waiting)
    monkeypatch.setattr(openai_adapter, "REQUEST_TIMEOUT", 0.1)
    assert chat._print_stream([]) == ""
    assert len(children) == 1
    assert children[0].poll() is not None
    assert "timed out" in capsys.readouterr().out


def test_openai_tool_limit_is_reported(monkeypatch) -> None:
    from hosaka.llm import openai_adapter

    monkeypatch.setattr(openai_adapter, "_api_key", lambda: "test")
    monkeypatch.setattr(
        openai_adapter,
        "_complete",
        lambda *a, **k: {
            "role": "assistant",
            "tool_calls": [
                {"id": "call", "function": {"name": "list_games", "arguments": "{}"}}
            ],
        },
    )
    text = "".join(openai_adapter.chat_stream([], tools=[{}], dispatch=lambda *a: "games"))
    assert "tool-call limit" in text


class TestOpenAIAvailability:
    def test_no_key_means_unavailable(self, tmp_path) -> None:
        with patch.dict(
            "os.environ",
            {
                "HOSAKA_LOCAL_FIRST": "0",
                "HOSAKA_STATE_PATH": str(tmp_path / "state.json"),
                "PICOCLAW_CONFIG_PATH": str(tmp_path / "missing-config.json"),
                "PICOCLAW_SECURITY_PATH": str(tmp_path / "missing-security.yml"),
            },
            clear=True,
        ):
            from hosaka.llm.openai_adapter import is_available
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            assert is_available() is False

    def test_key_means_available(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            from hosaka.llm.openai_adapter import is_available
            assert is_available() is True

    def test_ollama_local_first_counts_as_available(self, tmp_path) -> None:
        with patch.dict(
            "os.environ",
            {
                "HOSAKA_LOCAL_FIRST": "1",
                "PICOCLAW_CONFIG_PATH": str(tmp_path / "missing-config.json"),
                "PICOCLAW_SECURITY_PATH": str(tmp_path / "missing-security.yml"),
                "HOSAKA_STATE_PATH": str(tmp_path / "state.json"),
            },
            clear=True,
        ):
            from hosaka.llm.openai_adapter import _chat_url, _model, resolve_api_key

            key, source = resolve_api_key()
            assert key == "ollama"
            assert source == "openai-compatible default"
            assert _model() == "qwen2.5:0.5b"
            assert _chat_url() == "http://100.78.174.79:11434/v1/chat/completions"

    def test_openai_compatible_base_url_accepts_v1_suffix(self, tmp_path) -> None:
        with patch.dict(
            "os.environ",
            {
                "HOSAKA_STATE_PATH": str(tmp_path / "state.json"),
                "OPENAI_BASE_URL": "http://100.78.174.79:11434/v1",
                "OPENAI_MODEL": "qwen2.5:0.5b",
                "PICOCLAW_CONFIG_PATH": str(tmp_path / "missing-config.json"),
                "PICOCLAW_SECURITY_PATH": str(tmp_path / "missing-security.yml"),
            },
            clear=True,
        ):
            from hosaka.llm.openai_adapter import _chat_url, resolve_api_key

            key, source = resolve_api_key()
            assert key == "ollama"
            assert source == "openai-compatible default"
            assert _chat_url() == "http://100.78.174.79:11434/v1/chat/completions"

    def test_picoclaw_config_key_counts_as_available(self, tmp_path) -> None:
        cfg = {
            "agents": {"defaults": {"model_name": "gpt-4o-mini"}},
            "model_list": [
                {
                    "model_name": "gpt-4o-mini",
                    "model": "openai/gpt-4o-mini",
                    "api_key": "sk-from-picoclaw",
                }
            ],
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(cfg), encoding="utf-8")

        with patch.dict(
            "os.environ",
            {
                "PICOCLAW_CONFIG_PATH": str(config_path),
                "HOSAKA_STATE_PATH": str(tmp_path / "state.json"),
            },
            clear=True,
        ):
            from hosaka.llm.openai_adapter import is_available, resolve_api_key

            key, source = resolve_api_key()
            assert key == "sk-from-picoclaw"
            assert source == "~/.picoclaw/config.json"
            assert is_available() is True

    def test_env_key_beats_picoclaw_config(self, tmp_path) -> None:
        cfg = {
            "model_list": [
                {
                    "model_name": "gpt-4o-mini",
                    "api_key": "sk-from-picoclaw",
                }
            ]
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(cfg), encoding="utf-8")

        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-from-env",
                "PICOCLAW_CONFIG_PATH": str(config_path),
            },
            clear=True,
        ):
            from hosaka.llm.openai_adapter import resolve_api_key

            key, source = resolve_api_key()
            assert key == "sk-from-env"
            assert source == "env"


class TestLlmConfig:
    def test_llm_cli_list_and_scan_aliases(self) -> None:
        with patch("hosaka.llm_cli.show", return_value=0) as show:
            from hosaka.llm_cli import main

            assert main(["list"]) == 0
        show.assert_called_once()

        with patch("hosaka.llm_cli.use_ollama", return_value=0) as scan:
            assert main(["scan", "--use"]) == 0
        scan.assert_called_once_with("first")

    def test_replace_active_config_keeps_openai_profile(self) -> None:
        from hosaka.llm.llm_config import replace_active_config

        config = replace_active_config(
            {"provider": "openai", "api_key": "sk-test", "model": "gpt-4o-mini"},
            {"provider": "openai-compatible", "model": "qwen3:4b"},
        )

        assert config["profiles"]["openai"]["api_key"] == "sk-test"
        assert config["provider"] == "openai-compatible"

    def test_scan_llm_saves_first_discovery(self) -> None:
        with patch(
            "hosaka.scan.find_ollama_hosts",
            return_value=[{"base_url": "http://192.168.1.50:11434", "models": ["qwen3:4b"]}],
        ), patch("hosaka.scan.llm_config.load", return_value={}), patch(
            "hosaka.scan.llm_config.save"
        ) as save, patch("hosaka.scan.llm_config.apply_to_env"):
            from hosaka.scan import scan_llm

            assert scan_llm(use="first") == 0

        assert save.call_args.args[0]["base_url"] == "http://192.168.1.50:11434/v1"
        assert save.call_args.args[0]["model"] == "qwen3:4b"

    def test_discover_ollama_uses_tags_models(self) -> None:
        response = MagicMock()
        response.read.return_value = b'{"models":[{"name":"qwen3:4b"}]}'
        response.__enter__.return_value = response
        with patch("hosaka.llm.llm_config.urlopen", return_value=response) as mock_open:
            from hosaka.llm.llm_config import discover_ollama

            discovered = discover_ollama(["http://192.168.1.50:11434"])

        assert discovered == {
            "base_url": "http://192.168.1.50:11434",
            "models": ["qwen3:4b"],
        }
        mock_open.assert_called_once_with("http://192.168.1.50:11434/api/tags", timeout=1.5)

    def test_discovered_ollama_config_keeps_available_model(self) -> None:
        with patch(
            "hosaka.llm.llm_config.discover_ollama",
            return_value={"base_url": "http://127.0.0.1:11434", "models": ["qwen3:4b"]},
        ):
            from hosaka.llm.llm_config import discovered_ollama_config

            config = discovered_ollama_config({"model": "qwen3:4b"})

        assert config is not None
        assert config["base_url"] == "http://127.0.0.1:11434/v1"
        assert config["model"] == "qwen3:4b"
        assert config["ollama_discovery"] is True

    def test_openai_compatible_defaults_apply_to_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            from hosaka.llm.llm_config import apply_to_env

            apply_to_env({"provider": "openai-compatible"})

            import os

            assert os.environ["OPENAI_API_KEY"] == "ollama"
            assert os.environ["OPENAI_MODEL"] == "qwen2.5:0.5b"
            assert os.environ["OPENAI_BASE_URL"] == "http://100.78.174.79:11434/v1"

    def test_openai_config_preserves_explicit_cloud_values(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            from hosaka.llm.llm_config import apply_to_env

            apply_to_env(
                {
                    "provider": "openai",
                    "api_key": "sk-live",
                    "model": "gpt-4o-mini",
                    "base_url": "https://api.openai.com",
                }
            )

            import os

            assert os.environ["OPENAI_API_KEY"] == "sk-live"
            assert os.environ["OPENAI_MODEL"] == "gpt-4o-mini"
            assert os.environ["OPENAI_BASE_URL"] == "https://api.openai.com"


def test_chat_tool_schemas_share_reading_and_game_tools() -> None:
    from hosaka.voice.tools import chat_tool_schemas

    names = {item["function"]["name"] for item in chat_tool_schemas()}
    assert names == {"list_books", "open_reader", "list_games", "play_game"}


def test_chat_system_prompt_tells_model_to_use_play_tools() -> None:
    from hosaka.identity import build_chat_system_prompt

    prompt = build_chat_system_prompt(hostname="hosaka", cwd="/tmp")
    assert "list_games" in prompt
    assert "play_game" in prompt
    assert "list_books" in prompt
    assert "open_reader" in prompt


def test_openai_tool_loop_dispatches_play_game() -> None:
    from hosaka.llm import openai_adapter

    calls = {"n": 0}

    def fake_complete(messages, *, stream, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "play_game",
                            "arguments": '{"name": "tony hawk"}',
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "launching Tony Hawk."}

    seen: list[tuple[str, dict]] = []

    def dispatch(name: str, args: dict) -> str:
        seen.append((name, args))
        return "launching Tony Hawk's Pro Skater"

    with (
        patch.object(openai_adapter, "_api_key", return_value="sk-test"),
        patch.object(openai_adapter, "_complete", side_effect=fake_complete),
    ):
        text = "".join(
            openai_adapter.chat_stream(
                [{"role": "user", "content": "play tony hawk"}],
                tools=[{"type": "function", "function": {"name": "play_game"}}],
                dispatch=dispatch,
            )
        )
    assert seen == [("play_game", {"name": "tony hawk"})]
    assert "launching Tony Hawk" in text


def test_list_books_reads_real_library_shape(tmp_path, monkeypatch) -> None:
    from hosaka.voice import tools

    (tmp_path / "alice-in-wonderland.epub").write_bytes(b"epub")
    (tmp_path / "war-of-the-worlds.epub").write_bytes(b"epub")
    (tmp_path / "ignore.txt").write_text("not a book")
    monkeypatch.setenv("HOSAKA_BOOKS_DIR", str(tmp_path))

    result = tools.dispatch("list_books")

    assert result == "2 books available: Alice In Wonderland, War Of The Worlds"


def test_open_reader_uses_hosaka_foliate_launcher(monkeypatch) -> None:
    from hosaka.voice import tools

    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setenv("HOSAKA_CLI", "/home/operator/.local/bin/hosaka")

    def fake_popen(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return object()

    monkeypatch.setattr(tools.subprocess, "Popen", fake_popen)

    result = tools.dispatch("open_reader")

    assert result == "opening Foliate with the book library"
    assert calls[0][0] == [
        "/home/operator/.local/bin/hosaka",
        "launch",
        "foliate",
    ]
    assert calls[0][1]["start_new_session"] is True


def test_open_reader_opens_matching_ebook(tmp_path, monkeypatch) -> None:
    from hosaka.voice import tools

    book = tmp_path / "frankenstein.epub"
    book.write_bytes(b"epub")
    monkeypatch.setenv("HOSAKA_BOOKS_DIR", str(tmp_path))
    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(list(cmd))
        return object()

    monkeypatch.setattr(tools.subprocess, "Popen", fake_popen)

    result = tools.dispatch("open_reader", {"name": "frankenstein"})

    assert result == "opening Frankenstein in Foliate"
    assert calls[0][-1] == str(book)
    assert "com.github.johnfactotum.Foliate" in calls[0]
    assert not any(arg.endswith("/Books") or arg == str(tmp_path) for arg in calls[0][:-1])


def test_open_reader_reports_ambiguous_and_missing_titles(tmp_path, monkeypatch) -> None:
    from hosaka.voice import tools

    (tmp_path / "war-of-the-worlds.epub").write_bytes(b"epub")
    (tmp_path / "war-and-peace.epub").write_bytes(b"epub")
    monkeypatch.setenv("HOSAKA_BOOKS_DIR", str(tmp_path))
    monkeypatch.setattr(tools.subprocess, "Popen", lambda *a, **k: object())

    ambiguous = tools.dispatch("open_reader", {"name": "war"})
    missing = tools.dispatch("open_reader", {"name": "dune"})

    assert ambiguous.startswith("several matches:")
    assert "War Of The Worlds" in ambiguous
    assert "War And Peace" in ambiguous
    assert "no book matching 'dune'" in missing
    assert "2 books available" in missing


def test_select_llm_lists_fixed_saved_and_live_models(monkeypatch, capsys) -> None:
    from hosaka import llm_cli

    config = {
        "provider": "openai-compatible", "api_key": "ollama",
        "base_url": "http://localhost:11434/v1", "model": "qwen-old",
        "profiles": {"openai": {"provider": "openai", "model": "saved-cloud", "api_key": "secret"}},
    }
    monkeypatch.setattr(llm_cli.llm_config, "load", lambda: config)
    monkeypatch.setattr(llm_cli.llm_config, "ollama_discovery_urls", lambda: ["http://localhost:11434"])
    monkeypatch.setattr(
        llm_cli.llm_config, "discover_ollama",
        lambda *a, **k: {"models": ["qwen3:4b"], "base_url": "http://localhost:11434"},
    )
    assert llm_cli.select_llm() == 0
    out = capsys.readouterr().out
    assert "0 openai gpt-4.1" in out
    assert "saved-cloud" in out
    assert "qwen3:4b" in out
    assert "qwen-old" in out and "[unavailable" in out
    assert "secret" not in out
    assert len(llm_cli._selection_choices) == 6


def test_select_llm_openai_persists_and_clears_ollama_env(monkeypatch, tmp_path, capsys) -> None:
    from hosaka import llm_cli

    monkeypatch.setenv("HOSAKA_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_MODEL", "qwen3:4b")
    current = {
        "provider": "openai-compatible", "base_url": "http://localhost:11434/v1",
        "model": "qwen3:4b", "api_key": "ollama",
        "profiles": {"openai": {"provider": "openai", "api_key": "saved-key", "model": "gpt-4.1"}},
    }
    llm_cli.llm_config.save(current)
    monkeypatch.setattr(llm_cli, "_selection_choices", [
        llm_cli.LLMChoice("openai", "gpt-4.1", "https://api.openai.com"),
    ])
    assert llm_cli.select_llm("0") == 0
    config = llm_cli.llm_config.load()
    assert config["model"] == "gpt-4.1"
    assert config["provider"] == "openai"
    assert config["profiles"]["ollama"]["model"] == "qwen3:4b"
    import os
    assert os.environ["OPENAI_BASE_URL"] == "https://api.openai.com"
    assert os.environ["OPENAI_API_KEY"] == "saved-key"
    assert os.environ["OPENAI_MODEL"] == "gpt-4.1"
    assert "saved-key" not in capsys.readouterr().out


def test_select_llm_ollama_rechecks_displayed_host_and_saves_exact_model(monkeypatch) -> None:
    from hosaka import llm_cli

    monkeypatch.setattr(llm_cli, "_selection_choices", [
        llm_cli.LLMChoice("ollama", "qwen3:4b", "http://localhost:11434/v1"),
    ])
    with (
        patch.object(llm_cli.llm_config, "require_ollama", return_value={"models": ["qwen3:4b"]}) as guard,
        patch.object(llm_cli.llm_config, "load", return_value={}),
        patch.object(llm_cli.llm_config, "save") as save,
        patch.object(llm_cli.llm_config, "apply_to_env") as apply,
    ):
        assert llm_cli.select_llm("0") == 0
    guard.assert_called_once_with("http://localhost:11434/v1", "qwen3:4b")
    assert save.call_args.args[0]["model"] == "qwen3:4b"
    apply.assert_called_once_with(save.call_args.args[0])


@pytest.mark.parametrize("argument", ["-1", "99", "abc", "0 extra", "²"])
def test_select_llm_rejects_invalid_number(monkeypatch, capsys, argument) -> None:
    from hosaka import llm_cli

    monkeypatch.setattr(llm_cli, "_selection_choices", [
        llm_cli.LLMChoice("openai", "gpt-4.1", "https://api.openai.com"),
    ])
    with patch.object(llm_cli.llm_config, "save") as save:
        assert llm_cli.select_llm(argument) == 2
    save.assert_not_called()
    assert "/select llm" in capsys.readouterr().out


def test_select_llm_requires_listing_first(monkeypatch, capsys) -> None:
    from hosaka import llm_cli

    monkeypatch.setattr(llm_cli, "_selection_choices", None)
    assert llm_cli.select_llm("0") == 2
    assert "List choices first" in capsys.readouterr().out


def test_select_llm_unavailable_ollama_does_not_save(monkeypatch, capsys) -> None:
    from hosaka import llm_cli

    monkeypatch.setattr(llm_cli, "_selection_choices", [
        llm_cli.LLMChoice("ollama", "qwen3:4b", "http://localhost:11434/v1"),
    ])
    with (
        patch.object(llm_cli.llm_config, "discover_ollama", return_value=None),
        patch.object(llm_cli.llm_config, "save") as save,
        patch.object(llm_cli.llm_config, "apply_to_env") as apply,
    ):
        assert llm_cli.select_llm("0") == 1
    save.assert_not_called()
    apply.assert_not_called()
    assert "No chat request was sent" in capsys.readouterr().out


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("models", [None, ["other-model"]])
def test_ollama_guard_blocks_completion_requests(monkeypatch, stream, models) -> None:
    from hosaka.llm import llm_config, openai_adapter

    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_MODEL", "qwen3:4b")
    result = None if models is None else {"models": models}
    with (
        patch.object(llm_config, "discover_ollama", return_value=result) as probe,
        patch.object(openai_adapter.httpx, "Client") as client,
    ):
        if stream:
            text = "".join(openai_adapter.chat_stream([], tools=[{}], dispatch=lambda *a: ""))
            assert "chat failed: Ollama" in text
        else:
            with pytest.raises(RuntimeError, match="Ollama"):
                openai_adapter.chat_sync([])
    client.assert_not_called()
    probe.assert_called_once_with(["http://localhost:11434/v1"], timeout=1.0)


def test_ollama_guard_allows_installed_model_and_skips_openai(monkeypatch) -> None:
    from hosaka.llm import llm_config, openai_adapter

    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_MODEL", "qwen3:4b")
    with patch.object(llm_config, "discover_ollama", return_value={"models": ["qwen3:4b"]}) as probe:
        openai_adapter._assert_chat_backend()
        assert probe.call_count == 1
        monkeypatch.setenv("OPENAI_API_KEY", "cloud-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com")
        openai_adapter._assert_chat_backend()
        assert probe.call_count == 1


def test_provider_selection_save_failure_does_not_apply_or_claim_success(monkeypatch, capsys) -> None:
    from hosaka import llm_cli

    monkeypatch.setattr(llm_cli.llm_config, "load", lambda: {
        "provider": "openai", "api_key": "saved-key", "model": "gpt-4.1",
    })
    with (
        patch.object(llm_cli.llm_config, "save", side_effect=PermissionError("not writable")),
        patch.object(llm_cli.llm_config, "apply_to_env") as apply,
    ):
        with pytest.raises(PermissionError):
            llm_cli.use_openai("gpt-4.1")
    apply.assert_not_called()
    assert "Using OpenAI" not in capsys.readouterr().out


@pytest.mark.parametrize("key", ["stored-cloud-key", ""])
def test_select_openai_resolves_secret_despite_ollama_placeholder(monkeypatch, key, capsys) -> None:
    from hosaka import llm_cli
    from hosaka.llm import openai_adapter
    from hosaka.secrets import store

    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setattr(llm_cli.llm_config, "load", lambda: {"provider": "openai-compatible"})
    monkeypatch.setattr(store, "get", lambda name: key)
    monkeypatch.setattr(openai_adapter, "_load_picoclaw_config", lambda: {})
    monkeypatch.setattr(store, "import_from_picoclaw_security", lambda: (None, None))
    with (
        patch.object(llm_cli.llm_config, "save") as save,
        patch.object(llm_cli.llm_config, "apply_to_env") as apply,
    ):
        result = llm_cli.use_openai("gpt-4.1")
    out = capsys.readouterr().out
    if key:
        assert result == 0
        assert save.call_args.args[0]["api_key"] == key
        assert save.call_args.args[0]["model"] == "gpt-4.1"
        assert key not in out
    else:
        assert result == 1
        save.assert_not_called()
        apply.assert_not_called()
        assert "No OpenAI key" in out


def test_kiosk_can_restore_openai_from_operator_picoclaw_home(tmp_path, monkeypatch, capsys) -> None:
    from hosaka import llm_cli
    from hosaka.llm import openai_adapter
    from hosaka.secrets import store

    pico_home = tmp_path / "operator/.picoclaw"
    pico_home.mkdir(parents=True)
    (pico_home / "config.json").write_text(json.dumps({
        "agents": {"defaults": {"model_name": "gpt-4o-mini"}},
        "model_list": [{"model_name": "gpt-4o-mini", "model": "openai/gpt-4o-mini"}],
    }))
    (pico_home / ".security.yml").write_text(
        "model_list:\n  gpt-4o-mini:0:\n    api_keys:\n      - test-cloud-key\n"
    )
    monkeypatch.setenv("HOME", str(tmp_path / "root"))
    monkeypatch.setenv("PICOCLAW_HOME", str(pico_home))
    monkeypatch.delenv("PICOCLAW_CONFIG_PATH", raising=False)
    monkeypatch.delenv("PICOCLAW_SECURITY_PATH", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    monkeypatch.setattr(store, "get", lambda name: None)
    monkeypatch.setattr(llm_cli.llm_config, "load", lambda: {
        "provider": "openai-compatible", "api_key": "ollama",
    })
    with (
        patch.object(llm_cli.llm_config, "save") as save,
        patch.object(llm_cli.llm_config, "apply_to_env") as apply,
    ):
        assert llm_cli.use_openai("gpt-4.1") == 0
    assert save.call_args.args[0]["api_key"] == "test-cloud-key"
    apply.assert_called_once()
    assert "test-cloud-key" not in capsys.readouterr().out
    assert openai_adapter._picoclaw_config_path() == pico_home / "config.json"


def test_explicit_picoclaw_config_path_overrides_picoclaw_home(tmp_path, monkeypatch) -> None:
    from hosaka.llm import openai_adapter

    monkeypatch.setenv("PICOCLAW_HOME", str(tmp_path / "operator/.picoclaw"))
    monkeypatch.setenv("PICOCLAW_CONFIG_PATH", str(tmp_path / "custom/config.json"))
    assert openai_adapter._picoclaw_config_path() == tmp_path / "custom/config.json"
    assert openai_adapter._picoclaw_security_path() == tmp_path / "custom/.security.yml"


def test_non_ollama_compatible_profile_is_not_mislabeled_or_probed(monkeypatch, capsys) -> None:
    from hosaka import llm_cli

    config = {
        "provider": "openai-compatible", "model": "custom-model",
        "base_url": "http://localhost:1234/v1", "api_key": "custom-key",
    }
    monkeypatch.setattr(llm_cli.llm_config, "load", lambda: config)
    monkeypatch.setattr(llm_cli.llm_config, "ollama_discovery_urls", lambda: [])
    with patch.object(llm_cli.llm_config, "discover_ollama") as probe:
        assert llm_cli.select_llm() == 0
    probe.assert_not_called()
    out = capsys.readouterr().out
    assert "3 openai-compatible custom-model" in out
    assert "custom-key" not in out
    assert "custom-key" not in repr(llm_cli._selection_choices)
    with (
        patch.object(llm_cli.llm_config, "require_ollama") as guard,
        patch.object(llm_cli.llm_config, "save") as save,
        patch.object(llm_cli.llm_config, "apply_to_env"),
    ):
        assert llm_cli.select_llm("3") == 0
    guard.assert_not_called()
    assert save.call_args.args[0]["api_key"] == "custom-key"


def test_ollama_guard_refused_local_port_is_fast_without_post(monkeypatch) -> None:
    import socket
    from hosaka.llm import openai_adapter

    with socket.socket() as closed_port:
        closed_port.bind(("127.0.0.1", 0))
        port = closed_port.getsockname()[1]
        monkeypatch.setenv("OPENAI_API_KEY", "ollama")
        monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{port}/v1")
        monkeypatch.setenv("OPENAI_MODEL", "qwen3:4b")
        with patch.object(openai_adapter.httpx, "Client") as client:
            started = time.monotonic()
            with pytest.raises(RuntimeError, match="No chat request was sent"):
                openai_adapter.chat_sync([])
            assert time.monotonic() - started < 1.5
        client.assert_not_called()
