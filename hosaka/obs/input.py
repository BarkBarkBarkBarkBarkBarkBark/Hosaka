"""hosaka.obs.input — keystroke / command / UI event helpers.

Thin, opt-in convenience layer on top of `hosaka.obs.emit`. Lives here so the
TUI and web UI never have to think about event shape, privacy redaction, or
opt-out.

Hard rules (phase 09 of docs/increased_observability.yaml):

* Never log key contents inside a `secret` context. Only the buffer length.
* Never raise. All helpers wrap `emit` which is itself fail-silent.
* Honor HOSAKA_OBS_KEYSTROKES=off — when set, keystroke helpers no-op.
* Submitted commands ARE logged (with the resolved feature_id when known)
  because that's the most useful single signal we have for "what did the
  user do?".
"""
from __future__ import annotations

import os
from typing import Any, Optional

from hosaka.obs import emit

# ── env knobs ────────────────────────────────────────────────────────────────


def _keystrokes_enabled() -> bool:
    return os.getenv("HOSAKA_OBS_KEYSTROKES", "on").lower() not in (
        "0",
        "off",
        "false",
        "no",
    )


# Contexts that NEVER record key names, only buffer length.
_SECRET_CONTEXTS = frozenset(
    {
        "secret",
        "password",
        "api-token",
        "passphrase",
    }
)


def _normalize_key(key_name: str) -> str:
    """Pin the alphabet of recorded keys to a small set."""
    if not key_name:
        return "unknown"
    if len(key_name) == 1:
        return "printable"
    return key_name[:32]


# ── public helpers ───────────────────────────────────────────────────────────


def record_keystroke(
    key_name: str,
    *,
    context: str = "prompt",
    buffer_len: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> bool:
    """Record a single key press.

    For secret contexts: only buffer_len is recorded; key_name is dropped.
    Returns True if queued, False if disabled / dropped.
    """
    if not _keystrokes_enabled():
        return False
    is_secret = context in _SECRET_CONTEXTS
    payload: dict[str, Any] = {
        "context": context,
        "buffer_len": buffer_len,
    }
    if not is_secret:
        payload["key"] = _normalize_key(key_name)
    return emit(
        "KEYSTROKE",
        kind="keystroke",
        source="tui:input",
        level="debug",
        correlation_id=correlation_id,
        payload=payload,
    )


def record_command_submission(
    command_line: str,
    *,
    feature_id: Optional[str] = None,
    context: str = "prompt",
    correlation_id: Optional[str] = None,
) -> bool:
    """Record a submitted command line.

    The command line IS recorded (truncated by the sink's payload cap) because
    this is the most actionable single signal. If the user is inside a secret
    context (e.g. password prompt), only the length is recorded.
    """
    is_secret = context in _SECRET_CONTEXTS
    payload: dict[str, Any] = {"context": context}
    if is_secret:
        payload["length"] = len(command_line or "")
    else:
        payload["command_line"] = (command_line or "")[:1024]
    return emit(
        "COMMAND_SUBMITTED",
        kind="command",
        feature_id=feature_id,
        source="tui:prompt",
        level="info",
        status="ok",
        correlation_id=correlation_id,
        payload=payload,
    )


def record_ui_event(
    event_name: str,
    *,
    feature_id: Optional[str] = None,
    route: Optional[str] = None,
    target: Optional[str] = None,
    correlation_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> bool:
    """Record a frontend interaction (click / route change / feature invocation)."""
    payload: dict[str, Any] = {"event": event_name}
    if route:
        payload["route"] = route
    if target:
        payload["target"] = target
    if extra:
        payload["extra"] = extra
    return emit(
        event_name,
        kind="ui",
        feature_id=feature_id,
        source="web:ui",
        level="info",
        correlation_id=correlation_id,
        payload=payload,
    )


__all__ = [
    "record_keystroke",
    "record_command_submission",
    "record_ui_event",
]
