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
        mock_sync.assert_called_once_with("hello")

    def test_picoclaw_falls_back_to_openai(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        with (
            patch("hosaka.llm.picoclaw_adapter.chat_sync", side_effect=RuntimeError("fail")),
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
