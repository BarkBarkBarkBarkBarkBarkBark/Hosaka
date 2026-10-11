"""LLM router — Picoclaw first, OpenAI fallback, offline last resort."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Generator

from hosaka.llm import picoclaw_adapter
from hosaka.llm import openai_adapter
from hosaka.offline.assist import classify_intent

log = logging.getLogger("hosaka.router")


def _picoclaw_default_model() -> str:
    """Read the active Picoclaw default model (e.g. 'ollama/qwen2.5:0.5b')."""
    path = openai_adapter._picoclaw_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    default_alias = str(
        data.get("agents", {}).get("defaults", {}).get("model_name") or ""
    ).strip()
    if not default_alias:
        return ""
    model_list = data.get("model_list")
    if isinstance(model_list, list):
        for entry in model_list:
            if isinstance(entry, dict) and entry.get("model_name") == default_alias:
                return str(entry.get("model") or "").strip()
    return ""


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


def stream_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
    session: str | None = None,
    tools: list | None = None,
    dispatch=None,
) -> Generator[str, None, None]:
    """Stream tokens from the best available backend.

    Tries picoclaw → OpenAI → offline in priority order.
    Pass *backend* to force a specific backend.
    """
    chosen = backend or detect_backend()

    if chosen == LLMBackend.PICOCLAW and not tools:
        user_msg = _last_user_msg(messages)
        if user_msg:
            try:
                yield from picoclaw_adapter.chat_stream(user_msg, session=session)
                return
            except Exception as exc:
                log.warning("Picoclaw stream failed: %s — falling back", exc)

    if chosen in {LLMBackend.PICOCLAW, LLMBackend.OPENAI}:
        if openai_adapter.is_available():
            try:
                yield from openai_adapter.chat_stream(
                    messages, tools=tools, dispatch=dispatch
                )
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("OpenAI-compatible stream failed: %s — falling back", exc)
                yield f"(LLM connection failed: {exc}; using offline guidance.)\n"

    result = classify_intent(_last_user_msg(messages))
    yield f"[offline] {result.guidance}"


def sync_chat(
    messages: list[dict[str, str]],
    backend: str | None = None,
    session: str | None = None,
) -> str:
    """Single-string response from the best available backend."""
    chosen = backend or detect_backend()

    if chosen == LLMBackend.PICOCLAW:
        user_msg = _last_user_msg(messages)
        if user_msg:
            try:
                return picoclaw_adapter.chat_sync(user_msg, session=session)
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
    if backend == LLMBackend.PICOCLAW:
        model = _picoclaw_default_model()
        if model.startswith("ollama/"):
            return "Picoclaw -> Ollama"
        if model.startswith("openai/"):
            return "Picoclaw -> OpenAI"
        if model:
            return f"Picoclaw -> {model}"
        return "Picoclaw agent"
    if backend == LLMBackend.OPENAI:
        base = (os.getenv("OPENAI_BASE_URL") or "").strip().rstrip("/")
        if base and base != "https://api.openai.com":
            return "OpenAI-compatible (Ollama)"
        return "OpenAI API"
    if backend == LLMBackend.OFFLINE:
        return "Offline assist"
    return backend
