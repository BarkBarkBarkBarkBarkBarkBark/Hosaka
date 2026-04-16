"""LLM router — Picoclaw first, OpenAI fallback, offline last resort."""

from __future__ import annotations

import logging
import sys
from typing import Generator

from hosaka.llm import picoclaw_adapter
from hosaka.llm import openai_adapter
from hosaka.offline.assist import classify_intent

log = logging.getLogger("hosaka.router")


class LLMBackend:
    """Represents which LLM backend is active."""

    PICOCLAW = "picoclaw"
    OPENAI = "openai"
    OFFLINE = "offline"


def detect_backend() -> str:
    """Probe available backends and return the best one."""
    if picoclaw_adapter.is_available():
        return LLMBackend.PICOCLAW
    if openai_adapter.is_available():
        return LLMBackend.OPENAI
    return LLMBackend.OFFLINE


def shutdown_gateway() -> None:
    """No-op — picoclaw adapter is stateless (subprocess per call)."""
    pass


def _get_gateway():
    """Legacy compat shim — returns None, picoclaw adapter is stateless."""
    return None


def stream_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
) -> Generator[str, None, None]:
    """Stream tokens from the best available backend.

    Tries picoclaw → OpenAI → offline in priority order.
    Pass *backend* to force a specific backend.
    """
    chosen = backend or detect_backend()

    if chosen == LLMBackend.PICOCLAW:
        user_msg = _last_user_msg(messages)
        if user_msg:
            try:
                yield from picoclaw_adapter.chat_stream(user_msg)
                return
            except Exception as exc:
                log.warning("Picoclaw stream failed: %s — falling back", exc)

    if chosen in {LLMBackend.PICOCLAW, LLMBackend.OPENAI}:
        if openai_adapter.is_available():
            try:
                yield from openai_adapter.chat_stream(messages)
                return
            except Exception:  # noqa: BLE001
                pass

    result = classify_intent(_last_user_msg(messages))
    yield f"[offline] {result.guidance}"


def sync_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
) -> str:
    """Single-string response from the best available backend."""
    chosen = backend or detect_backend()

    if chosen == LLMBackend.PICOCLAW:
        user_msg = _last_user_msg(messages)
        if user_msg:
            try:
                return picoclaw_adapter.chat_sync(user_msg)
            except Exception as exc:
                log.warning("Picoclaw sync failed: %s — falling back", exc)

    if chosen in {LLMBackend.PICOCLAW, LLMBackend.OPENAI}:
        if openai_adapter.is_available():
            try:
                return openai_adapter.chat_sync(messages)
            except Exception:  # noqa: BLE001
                pass

    result = classify_intent(_last_user_msg(messages))
    return f"[offline] {result.guidance}"


def _last_user_msg(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def backend_display_name(backend: str) -> str:
    return {
        LLMBackend.PICOCLAW: "Picoclaw agent",
        LLMBackend.OPENAI: "OpenAI API",
        LLMBackend.OFFLINE: "Offline assist",
    }.get(backend, backend)
