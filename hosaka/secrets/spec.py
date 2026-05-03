"""Declarative spec of every env var Hosaka cares about.

Derived from the ``os.getenv`` audit across the codebase. Required keys
are surfaced by ``hosaka secrets check`` and ``hosaka doctor`` with a
concrete remediation; optional keys are listed for visibility but won't
fail a check when unset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Key:
    name: str
    purpose: str = ""
    default: str | None = None
    secret: bool = True
    validator: Callable[[str], str | None] | None = None
    probe: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


def starts_with(prefix: str) -> Callable[[str], str | None]:
    def _check(value: str) -> str | None:
        if not value.startswith(prefix):
            return f"expected value to start with {prefix!r}"
        return None
    return _check


def non_empty(value: str) -> str | None:
    return None if value.strip() else "value is empty"


REQUIRED: tuple[Key, ...] = (
    Key(
        name="OPENAI_API_KEY",
        purpose="OpenAI Realtime + chat + Whisper",
        validator=starts_with("sk-"),
        probe="openai_chat_models",
    ),
)


OPTIONAL: tuple[Key, ...] = (
    Key(
        name="OPENAI_BASE_URL",
        purpose="Override the OpenAI API base (proxy / Azure / vLLM)",
        default="https://api.openai.com",
        secret=False,
    ),
    Key(
        name="OPENAI_MODEL",
        purpose="Default OpenAI chat model id",
        default="gpt-4o-mini",
        secret=False,
    ),
    Key(
        name="HOSAKA_VOICE_MODEL",
        purpose="Realtime model id (gpt-realtime by default)",
        default="gpt-realtime",
        secret=False,
    ),
    Key(
        name="HOSAKA_VOICE_VOICE",
        purpose="Realtime voice id (marin/cedar/alloy/...)",
        default="marin",
        secret=False,
    ),
    Key(
        name="HOSAKA_VOICE_TRANSCRIBE_MODEL",
        purpose="Whisper model used by the voice agent fallback",
        default="whisper-1",
        secret=False,
    ),
    Key(
        name="PICOCLAW_SESSION",
        purpose="Session key used by hosaka chat / voice -> picoclaw",
        default="hosaka:main",
        secret=False,
    ),
    Key(
        name="PICOCLAW_MODEL",
        purpose="Override the picoclaw model (matched against config.json model_list)",
        secret=False,
    ),
    Key(
        name="HOSAKA_API_TOKEN",
        purpose="Bearer token for non-loopback /api/v1 calls",
        validator=non_empty,
    ),
    Key(
        name="PICOCLAW_GATEWAY_TOKEN",
        purpose="Token presented to the picoclaw gateway",
        validator=non_empty,
    ),
    Key(
        name="PICOCLAW_GATEWAY_PASSWORD",
        purpose="Password for the picoclaw gateway when token-less",
        validator=non_empty,
    ),
    Key(
        name="HOSAKA_WEB_HOST",
        purpose="Web bind host (127.0.0.1 by default; set to 0.0.0.0 for tailnet)",
        default="127.0.0.1",
        secret=False,
    ),
    Key(
        name="HOSAKA_PUBLIC_MODE",
        purpose="When 1, voice/agent surfaces fail closed",
        secret=False,
    ),
)


def all_keys() -> tuple[Key, ...]:
    return REQUIRED + OPTIONAL


def find(name: str) -> Key | None:
    for key in all_keys():
        if key.name == name or name in key.aliases:
            return key
    return None
