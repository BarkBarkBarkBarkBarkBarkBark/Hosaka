"""Picoclaw adapter — calls `picoclaw agent` as a subprocess.

Picoclaw (https://github.com/sipeed/picoclaw) is a channel-based local agent.
It does not expose an OpenClaw-compatible WebSocket RPC interface.
This adapter drives the `picoclaw agent` CLI directly.

Key facts:
- `picoclaw agent -m "..." --session KEY` sends one message and exits.
- Session key persists conversation history across calls.
- Output: ANSI banner lines + a response line prefixed with "🦞 ".
- Streaming: we yield the response text word-by-word for a streaming feel.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Generator

PICOCLAW_BIN = "picoclaw"
DEFAULT_SESSION = os.getenv("PICOCLAW_SESSION", "hosaka:main")
DEFAULT_MODEL = os.getenv("PICOCLAW_MODEL", "")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
_RESPONSE_PREFIX = "🦞"


def is_available() -> bool:
    return bool(shutil.which(PICOCLAW_BIN))


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _extract_response(raw_output: str) -> str:
    """Pull the agent response out of picoclaw's decorated output."""
    for line in raw_output.splitlines():
        clean = _strip_ansi(line).strip()
        if clean.startswith(_RESPONSE_PREFIX):
            return clean[len(_RESPONSE_PREFIX):].strip()
    # Fallback: return everything that isn't the banner
    lines = [
        _strip_ansi(l).strip()
        for l in raw_output.splitlines()
        if _strip_ansi(l).strip()
        and not _strip_ansi(l).strip().startswith("█")
        and "picoclaw" not in _strip_ansi(l).lower()
        and "Interactive mode" not in _strip_ansi(l)
        and "Goodbye" not in _strip_ansi(l)
        and "Ctrl+C" not in _strip_ansi(l)
    ]
    return " ".join(lines)


def chat_sync(message: str, session: str | None = None) -> str:
    """Send a message to picoclaw and return the response text."""
    session = session or DEFAULT_SESSION
    cmd = [PICOCLAW_BIN, "agent", "-m", message, "--session", session]
    if DEFAULT_MODEL:
        cmd += ["--model", DEFAULT_MODEL]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return _extract_response(output) or "[picoclaw: empty response]"
    except subprocess.TimeoutExpired:
        return "[picoclaw: timed out]"
    except Exception as exc:  # noqa: BLE001
        return f"[picoclaw error: {exc}]"


def chat_stream(message: str, session: str | None = None) -> Generator[str, None, None]:
    """Send a message and yield response tokens (word-by-word streaming)."""
    response = chat_sync(message, session=session)
    # Yield word by word for a streaming feel in the TUI
    words = response.split(" ")
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
