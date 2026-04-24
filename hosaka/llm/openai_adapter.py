"""OpenAI API adapter — fallback when picoclaw / gateway is unavailable."""

from __future__ import annotations

import json
import os
from typing import Generator

import httpx

_OPENAI_DEFAULT_BASE = "https://api.openai.com"
REQUEST_TIMEOUT = float(os.getenv("HOSAKA_CHAT_TIMEOUT", "120"))


def _base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", _OPENAI_DEFAULT_BASE).rstrip("/")


def _chat_url() -> str:
    return f"{_base_url()}/v1/chat/completions"


def _api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def _model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def is_available() -> bool:
    """Return True if OPENAI_API_KEY is set."""
    return bool(_api_key())


def chat_stream(messages: list[dict[str, str]]) -> Generator[str, None, None]:
    """Stream chat completion tokens from OpenAI."""
    key = _api_key()
    if not key:
        yield "OPENAI_API_KEY is not set."
        return
    payload = {
        "model": _model(),
        "messages": messages,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        with client.stream("POST", _chat_url(), json=payload, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def chat_sync(messages: list[dict[str, str]]) -> str:
    """Non-streaming chat completion from OpenAI."""
    key = _api_key()
    if not key:
        return "OPENAI_API_KEY is not set."
    payload = {
        "model": _model(),
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.post(OPENAI_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
