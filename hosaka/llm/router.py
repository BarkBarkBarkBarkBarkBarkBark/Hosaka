"""LLM router — OpenClaw first, OpenAI fallback, offline last resort."""

from __future__ import annotations

import logging
import sys
from typing import Generator

from hosaka.llm import openclaw  # is_available() only — gateway probing
from hosaka.llm import openai_adapter
from hosaka.llm.gateway import GatewayAdapter
from hosaka.offline.assist import classify_intent

log = logging.getLogger("hosaka.gateway")

# Module-level adapter — lazy-initialized on first OpenClaw use
_gateway: GatewayAdapter | None = None


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


def _get_gateway() -> GatewayAdapter | None:
    """Lazy-init the gateway adapter. Returns None on failure."""
    global _gateway
    if _gateway is not None and _gateway.is_ready:
        return _gateway
    if not GatewayAdapter.is_available():
        return None
    try:
        _gateway = GatewayAdapter()
        _gateway.connect()
        return _gateway
    except Exception as exc:
        log.warning("Gateway connect failed: %s", exc)
        _gateway = None
        return None


def shutdown_gateway() -> None:
    """Disconnect the module-level gateway adapter."""
    global _gateway
    if _gateway is not None:
        try:
            _gateway.disconnect()
        except Exception:
            pass
        _gateway = None


def stream_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
) -> Generator[str, None, None]:
    """Stream tokens from the best available backend.

    Tries OpenClaw gateway → OpenAI → offline stub in priority order.
    Pass *backend* to force a specific backend.
    """
    chosen = backend or detect_backend()

    # Prefer the OpenClaw gateway WS client for full agent tooling.
    if chosen == LLMBackend.OPENCLAW:
        gw = _get_gateway()
        if gw is not None:
            try:
                # Extract last user message for gateway chat.send
                user_msg = ""
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_msg = msg.get("content", "")
                        break
                if user_msg:
                    yield from gw.chat_stream(user_msg)
                    return
            except Exception as exc:
                log.warning("Gateway stream failed: %s — falling back", exc)

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

    # Prefer the OpenClaw gateway WS client for full agent tooling.
    if chosen == LLMBackend.OPENCLAW:
        gw = _get_gateway()
        if gw is not None:
            try:
                user_msg = ""
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        user_msg = msg.get("content", "")
                        break
                if user_msg:
                    return gw.chat_sync(user_msg)
            except Exception as exc:
                log.warning("Gateway sync failed: %s — falling back", exc)

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
