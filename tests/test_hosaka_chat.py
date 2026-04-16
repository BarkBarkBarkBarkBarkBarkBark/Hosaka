"""Tests for the LLM router, chat module, and gateway adapter."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, PropertyMock
import hosaka.llm.router as router_mod
from hosaka.llm.router import LLMBackend, detect_backend, sync_chat


class TestDetectBackend:
    def test_openclaw_preferred(self) -> None:
        with patch("hosaka.llm.openclaw.is_available", return_value=True):
            assert detect_backend() == LLMBackend.OPENCLAW

    def test_openai_fallback(self) -> None:
        with (
            patch("hosaka.llm.openclaw.is_available", return_value=False),
            patch("hosaka.llm.openai_adapter.is_available", return_value=True),
        ):
            assert detect_backend() == LLMBackend.OPENAI

    def test_offline_last_resort(self) -> None:
        with (
            patch("hosaka.llm.openclaw.is_available", return_value=False),
            patch("hosaka.llm.openai_adapter.is_available", return_value=False),
        ):
            assert detect_backend() == LLMBackend.OFFLINE


class TestSyncChat:
    def setup_method(self):
        # Reset the module-level gateway between tests
        router_mod._gateway = None

    def test_openclaw_gateway_used_when_available(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        mock_gw = MagicMock()
        mock_gw.is_ready = True
        mock_gw.chat_sync.return_value = "gateway response"

        with (
            patch("hosaka.llm.openclaw.is_available", return_value=True),
            patch.object(router_mod, "_gateway", mock_gw),
        ):
            result = sync_chat(messages, backend=LLMBackend.OPENCLAW)
        assert result == "gateway response"
        mock_gw.chat_sync.assert_called_once_with("hello")

    def test_openclaw_falls_back_to_openai_when_gw_unavailable(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        with (
            patch("hosaka.llm.openclaw.is_available", return_value=True),
            patch("hosaka.llm.gateway.GatewayAdapter.is_available", return_value=False),
            patch("hosaka.llm.openai_adapter.is_available", return_value=True),
            patch("hosaka.llm.openai_adapter.chat_sync", return_value="openai response"),
        ):
            result = sync_chat(messages, backend=LLMBackend.OPENCLAW)
        assert result == "openai response"

    def test_offline_fallback_uses_intent(self) -> None:
        messages = [{"role": "user", "content": "help me get on wifi"}]
        with (
            patch("hosaka.llm.openclaw.is_available", return_value=False),
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
    def test_no_key_means_unavailable(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            from hosaka.llm.openai_adapter import is_available
            # Remove key if present
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            assert is_available() is False

    def test_key_means_available(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            from hosaka.llm.openai_adapter import is_available
            assert is_available() is True
