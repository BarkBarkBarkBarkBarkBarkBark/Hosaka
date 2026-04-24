"""Tool surface exposed to the OpenAI Realtime session.

Single source of truth for both clients:

* The headless Python daemon in :mod:`hosaka.voice.daemon` imports
  :data:`TOOL_SCHEMAS` at session-open time and calls :func:`dispatch`
  when the model emits a ``response.function_call_arguments.done`` event.
* The browser voice client fetches the same schema from
  ``/api/v1/voice/ephemeral-token`` and POSTs back to
  ``/api/v1/voice/tools/{name}`` to run the tool server-side.

Keeping the schema + dispatcher in one file means the two clients stay
in lock-step: adding a tool here makes it available everywhere.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any, Callable

from hosaka.identity import build_voice_system_prompt

log = logging.getLogger("hosaka.voice.tools")

# ── storage for voice-added todos ────────────────────────────────────────

# The frontend TodoPanel is localStorage-only. Rather than rewrite it to
# use a server store, voice-added todos land in a dedicated JSONL the
# VoicePanel polls and mirrors into its own `hosaka:todo-add` event bus.
# That keeps voice adds visible without breaking the existing Todo UX.
TODO_STORE = Path(
    os.getenv(
        "HOSAKA_VOICE_TODO_STORE",
        str(Path.home() / ".hosaka" / "voice_todos.jsonl"),
    )
)


# ── the schema sent to Realtime ──────────────────────────────────────────

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "todo_add",
        "description": (
            "Add a single-line open loop to the operator's todo list. "
            "Use for short action items ('buy coffee', 'call mom'). "
            "Keep it under 120 characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The loop text, as a short imperative.",
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "set_mode",
        "description": (
            "Switch Hosaka between console (kiosk UI, lower free RAM) "
            "and device (build/SSH-friendly) mode. Rarely useful; do "
            "not call unless the operator explicitly asks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["console", "device"]},
                "persist": {"type": "boolean", "default": False},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_status",
        "description": (
            "One-line snapshot of this Hosaka appliance: mode, uptime, "
            "free RAM, IP, CPU temperature. Use when the operator asks "
            "'how are you' or similar device-health questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "see",
        "description": (
            "Grab a single frame from the attached USB webcam and have "
            "a vision model describe it, answering `prompt`. Use for "
            "'what do you see', 'read this label', 'is the cat here'. "
            "Takes 1-3 seconds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Question for the vision model. Defaults to "
                        "'describe what you see'."
                    ),
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "ask_agent",
        "description": (
            "Hand a prompt to the full Hosaka/picoclaw agent. Use for "
            "anything that needs tool use the Realtime session doesn't "
            "have: running shell commands, editing files, web search, "
            "git, package installs, code review. Slow (1-30 seconds) — "
            "say 'on it' to the operator BEFORE calling, then relay the "
            "agent's reply once it returns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Full user intent, in plain English.",
                }
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
]


SYSTEM_INSTRUCTIONS = build_voice_system_prompt()


# ── dispatcher ───────────────────────────────────────────────────────────


def _append_todo(text: str) -> dict[str, Any]:
    TODO_STORE.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "id": f"v{int(time.time() * 1000)}",
        "at": int(time.time()),
        "text": text.strip()[:200],
        "source": "voice",
    }
    with TODO_STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_voice_todos(limit: int = 50) -> list[dict[str, Any]]:
    if not TODO_STORE.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in TODO_STORE.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def _tool_todo_add(args: dict[str, Any]) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        return "todo_add: empty text, ignored"
    row = _append_todo(text)
    log.info("voice todo added: %s", text)
    return f"added: {row['text']}"


def _tool_set_mode(args: dict[str, Any]) -> str:
    mode = str(args.get("mode", "")).strip()
    persist = bool(args.get("persist", False))
    if mode not in {"console", "device"}:
        return f"set_mode: unknown mode {mode!r}"
    import subprocess
    cli = os.getenv("HOSAKA_CLI", "/usr/local/bin/hosaka")
    if not Path(cli).exists():
        return f"set_mode: {cli} not installed on this host"
    cmd = [cli, "mode", mode] + (["--persist"] if persist else [])
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return f"set_mode: failed to spawn ({exc})"
    return f"switching to {mode} mode" + (" (persisted)" if persist else "")


def _tool_get_status(_: dict[str, Any]) -> str:
    mem_total_mb = mem_free_mb = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, val = line.partition(":")
            num = val.strip().split()[0]
            if key == "MemTotal":
                mem_total_mb = int(num) // 1024
            elif key == "MemAvailable":
                mem_free_mb = int(num) // 1024
    except (OSError, ValueError):
        pass
    uptime_s = 0
    try:
        uptime_s = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError):
        pass
    temp_c: float | None = None
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        temp_c = round(int(raw) / 1000.0, 1)
    except (OSError, ValueError):
        pass
    hours = uptime_s // 3600
    mins = (uptime_s % 3600) // 60
    parts = [
        f"host {socket.gethostname()}",
        f"up {hours}h{mins}m",
        f"free {mem_free_mb} of {mem_total_mb} MB",
    ]
    if temp_c is not None:
        parts.append(f"cpu {temp_c} C")
    return "; ".join(parts)


def _tool_see(args: dict[str, Any]) -> str:
    prompt = str(args.get("prompt", "")).strip() or "describe what you see"
    try:
        from hosaka.voice import camera, vision
    except ImportError as exc:
        return f"see: voice deps not installed ({exc})"
    try:
        frame = camera.snapshot_jpeg()
    except Exception as exc:  # noqa: BLE001
        return f"see: camera unavailable ({exc})"
    try:
        return vision.describe(frame, prompt=prompt)
    except Exception as exc:  # noqa: BLE001
        return f"see: vision call failed ({exc})"


def _tool_ask_agent(args: dict[str, Any]) -> str:
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return "ask_agent: empty prompt"
    try:
        from hosaka.llm import picoclaw_adapter
    except ImportError as exc:
        return f"ask_agent: picoclaw adapter missing ({exc})"
    if not picoclaw_adapter.is_available():
        from hosaka.llm import openai_adapter
        if not openai_adapter.is_available():
            return "ask_agent: no backend available"
        try:
            return openai_adapter.chat_sync(
                [{"role": "user", "content": prompt}]
            )[:1500]
        except Exception as exc:  # noqa: BLE001
            return f"ask_agent: openai call failed ({exc})"
    try:
        return picoclaw_adapter.chat_sync(prompt)[:1500]
    except Exception as exc:  # noqa: BLE001
        return f"ask_agent: picoclaw failed ({exc})"


_DISPATCH: dict[str, Callable[[dict[str, Any]], str]] = {
    "todo_add": _tool_todo_add,
    "set_mode": _tool_set_mode,
    "get_status": _tool_get_status,
    "see": _tool_see,
    "ask_agent": _tool_ask_agent,
}


def dispatch(name: str, args: dict[str, Any] | None = None) -> str:
    """Run tool ``name`` with ``args`` and return a short user-facing string.

    The return value is fed back into the Realtime session as the
    function output, so keep it compact — the model will read it aloud
    (or summarise it). Errors are returned as plain strings rather than
    raised so the session doesn't wedge on a stack trace.
    """
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"unknown tool: {name}"
    try:
        return fn(args or {})
    except Exception as exc:  # noqa: BLE001
        log.exception("tool %s crashed", name)
        return f"{name}: crashed ({exc})"
