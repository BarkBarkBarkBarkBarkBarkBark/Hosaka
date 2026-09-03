"""Tests for the LLM router, chat module, and adapters."""

from __future__ import annotations

import json
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


def test_conversational_backend_prefers_openai() -> None:
    from hosaka.llm import chat as chat_mod

    with (
        patch.object(chat_mod.openai_adapter, "is_available", return_value=True),
        patch.object(chat_mod.picoclaw_adapter, "is_available", return_value=True),
    ):
        assert chat_mod._conversational_backend() == LLMBackend.OPENAI


class TestOpenAIAvailability:
    def test_no_key_means_unavailable(self, tmp_path) -> None:
        with patch.dict(
            "os.environ",
            {
                "HOSAKA_LOCAL_FIRST": "0",
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
            {"PICOCLAW_CONFIG_PATH": str(config_path)},
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
