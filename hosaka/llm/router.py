"""LLM router — OpenClaw first, OpenAI fallback, offline last resort."""

from __future__ import annotations

import sys
from typing import Generator

from hosaka.llm import openclaw  # is_available() only — gateway probing
from hosaka.llm import openai_adapter
from hosaka.offline.assist import classify_intent


class LLMBackend:
    """Represents which LLM backend is active."""

    OPENCLAW = "openclaw"
    OPENAI = "openai"
    OFFLINE = "offline"


def detect_backend() -> str:
    """Probe available backends and return the best one."""
    if openclaw.is_available():
        return LLMBackend.OPENCLAW
    if openai_adapter.is_available():
        return LLMBackend.OPENAI
    return LLMBackend.OFFLINE


def stream_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
) -> Generator[str, None, None]:
    """Stream tokens from the best available backend.

    Tries OpenClaw → OpenAI → offline stub in priority order.
    Pass *backend* to force a specific backend.
    """
    chosen = backend or detect_backend()

    # The OpenClaw gateway speaks WebSocket, not REST — stream_chat() routes
    # directly to openai_adapter for one-shot calls.  Interactive agent chat
    # is handled by `openclaw tui` in chat.py:enter_chat_mode().
    if chosen in {LLMBackend.OPENCLAW, LLMBackend.OPENAI}:
        if openai_adapter.is_available():
            try:
                yield from openai_adapter.chat_stream(messages)
                return
            except Exception:  # noqa: BLE001
                pass

    # Offline fallback — use the last user message for intent matching
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break
    result = classify_intent(last_user_msg)
    yield f"[offline] {result.guidance}"


def sync_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
) -> str:
    """Single-string response from the best available backend."""
    chosen = backend or detect_backend()

    # Same routing as stream_chat — OpenClaw gateway is for interactive TUI;
    # one-shot sync goes through openai_adapter.
    if chosen in {LLMBackend.OPENCLAW, LLMBackend.OPENAI}:
        if openai_adapter.is_available():
            try:
                return openai_adapter.chat_sync(messages)
            except Exception:  # noqa: BLE001
                pass

    last_user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "")
            break
    result = classify_intent(last_user_msg)
    return f"[offline] {result.guidance}"


def backend_display_name(backend: str) -> str:
    return {
        LLMBackend.OPENCLAW: "OpenClaw gateway",
        LLMBackend.OPENAI: "OpenAI API",
        LLMBackend.OFFLINE: "Offline assist",
    }.get(backend, backend)
