"""Tests for the LLM router and chat module."""

from __future__ import annotations

from unittest.mock import patch

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
