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
            "Hand a prompt to the full Hosaka/picoclaw agent. This is the "
            "default path for filesystem changes, file creation, codebase "
            "inspection, shell commands, git, package installs, web search, "
            "and any request that depends on the real machine state instead "
            "of general knowledge. Slow (1-30 seconds) — say 'on it' to the "
            "operator BEFORE calling, then relay the agent's reply once it returns."
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
    {
        "type": "function",
        "name": "write_doc",
        "description": (
            "Save a markdown document to the operator's docs folder. Use when "
            "the operator asks you to 'write up', 'save a note', 'make a summary', "
            "'commit a doc', etc. Always include a top-level '# heading'. Path "
            "is relative; '.md' is added automatically. Speak the saved filename "
            "back so the operator knows where it landed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative filename, e.g. '2026-05-02-summary' or 'projects/cyberdeck'.",
                },
                "body": {
                    "type": "string",
                    "description": "Full markdown body. Start with '# title'.",
                },
            },
            "required": ["path", "body"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "append_doc",
        "description": (
            "Append markdown to an existing doc (or create it if missing). Use "
            "for ongoing journals, running todo lists, or follow-up notes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["path", "body"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "write_doc_template",
        "description": (
            "Save a doc using a built-in template. Pick 'summary' for a recap "
            "with key points + next steps, 'todo' for a checkbox list, or "
            "'note' for a freeform entry. Pass `body` with the raw content; the "
            "template adds the heading, timestamp, and structure."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template": {"type": "string", "enum": ["summary", "todo", "note"]},
                "title": {"type": "string", "description": "Human title for the heading."},
                "slug": {"type": "string", "description": "Optional filename slug; auto-derived from title."},
                "body": {"type": "string", "description": "Raw content the template wraps."},
            },
            "required": ["template", "title"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_docs",
        "description": (
            "List the operator's saved markdown docs (path, title, mtime). "
            "Use when the operator asks 'what notes do i have' or 'find the "
            "summary from last week'."
        ),
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 20}},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_doc",
        "description": (
            "Read a saved doc by relative path. Use when the operator asks you "
            "to recall, summarise, or quote one of their notes."
        ),
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]


SYSTEM_INSTRUCTIONS = build_voice_system_prompt()

VOICE_AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "spoken": {
            "type": "string",
            "description": "What Hosaka should say back to the operator out loud or show as the main reply.",
        },
        "thought": {
            "type": "string",
            "description": "Short quiet status note for the transcript. Do not expose detailed chain-of-thought.",
        },
        "did_work": {
            "type": "boolean",
            "description": "Whether tools or real machine actions were used.",
        },
    },
    "required": ["spoken"],
}


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
        return "ask_agent: picoclaw is unavailable on this host"
    try:
        return picoclaw_adapter.chat_sync(prompt)[:1500]
    except Exception as exc:  # noqa: BLE001
        return f"ask_agent: picoclaw failed ({exc})"


# ── docs tools ──────────────────────────────────────────────────────────


def _tool_write_doc(args: dict[str, Any]) -> str:
    path = str(args.get("path", "")).strip()
    body = str(args.get("body", ""))
    if not path or not body.strip():
        return "write_doc: need both path and body"
    from hosaka.web.docs_api import write_doc_simple
    try:
        out = write_doc_simple(path, body, append=False)
    except Exception as exc:  # noqa: BLE001
        return f"write_doc: failed ({exc})"
    return f"saved {out['path']} ({out['bytes']} bytes)"


def _tool_append_doc(args: dict[str, Any]) -> str:
    path = str(args.get("path", "")).strip()
    body = str(args.get("body", ""))
    if not path or not body.strip():
        return "append_doc: need both path and body"
    from hosaka.web.docs_api import write_doc_simple
    try:
        out = write_doc_simple(path, body, append=True)
    except Exception as exc:  # noqa: BLE001
        return f"append_doc: failed ({exc})"
    return f"appended to {out['path']} ({out['bytes']} bytes total)"


def _tool_write_doc_template(args: dict[str, Any]) -> str:
    tpl = str(args.get("template", "")).strip()
    if tpl not in {"summary", "todo", "note"}:
        return f"write_doc_template: unknown template {tpl!r}"
    title = str(args.get("title", "")).strip() or tpl
    slug = str(args.get("slug", "")).strip() or None
    body = str(args.get("body", "")) or None
    from hosaka.web.docs_api import write_template_simple
    try:
        out = write_template_simple(tpl, slug=slug, title=title, body=body)
    except Exception as exc:  # noqa: BLE001
        return f"write_doc_template: failed ({exc})"
    return f"saved {out['path']} from {tpl} template"


def _tool_list_docs(args: dict[str, Any]) -> str:
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    from hosaka.web.docs_api import list_docs_summary
    try:
        rows = list_docs_summary(limit=limit)
    except Exception as exc:  # noqa: BLE001
        return f"list_docs: failed ({exc})"
    if not rows:
        return "no docs yet"
    lines = [f"{r['path']} — {r['title']}" for r in rows]
    return "\n".join(lines)


def _tool_read_doc(args: dict[str, Any]) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return "read_doc: need path"
    from hosaka.web.docs_api import read_doc_simple
    try:
        out = read_doc_simple(path)
    except Exception as exc:  # noqa: BLE001
        return f"read_doc: failed ({exc})"
    body = out.get("body", "")
    if len(body) > 4000:
        body = body[:4000] + "\n\n… (truncated)"
    return body


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    cleaned = _strip_code_fence(text)
    try:
        payload = json.loads(cleaned)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(cleaned[start : end + 1])
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def run_agent_voice_turn(operator_text: str) -> dict[str, Any]:
    """Run one voice-originated agent turn through PicoClaw and format it.

    Returns a small structured payload for transcript vs spoken response.
    """
    text = operator_text.strip()
    if not text:
        return {
            "operator_text": "",
            "spoken": "i didn't catch that.",
            "thought": "empty transcription",
            "did_work": False,
            "raw": "",
        }

    try:
        from hosaka.llm import picoclaw_adapter
    except ImportError as exc:
        return {
            "operator_text": text,
            "spoken": "the local agent stack is unavailable right now.",
            "thought": f"picoclaw adapter missing ({exc})",
            "did_work": False,
            "raw": "",
        }

    if not picoclaw_adapter.is_available():
        return {
            "operator_text": text,
            "spoken": "the local agent is not installed on this host.",
            "thought": "picoclaw unavailable",
            "did_work": False,
            "raw": "",
        }

    prompt = (
        "you are hosaka handling a voice command from the operator.\n"
        "perform real work if needed using your normal tools and workspace access.\n"
        "for filesystem edits, shell commands, repo inspection, environment checks, or long tasks, actually do the work instead of describing how.\n"
        "if the operator asks you to 'write up', 'save a note', 'make a summary', 'commit a doc', or similar, save a markdown file under the docs folder (~/.picoclaw/workspace/memory by default) and mention the filename in `spoken` so they know where it landed. include a top-level '# heading' and use sections, bold, and checkbox lists where helpful.\n"
        "then return strict json only, with no markdown fences, matching this schema:\n"
        f"{json.dumps(VOICE_AGENT_SCHEMA, ensure_ascii=False)}\n"
        "rules:\n"
        "- `spoken` is concise, operator-facing, natural speech: one to three sentences.\n"
        "- `thought` is a short quiet transcript note such as 'created test.md in home directory' or 'checking repo status'.\n"
        "- do not expose chain-of-thought. summarize actions/results only.\n"
        "- if you completed a request, say so clearly in `spoken`.\n"
        "- if you need more time, say what is happening briefly in `spoken` and summarize the current action in `thought`.\n"
        "- if no hidden note is useful, set `thought` to an empty string.\n"
        "operator request:\n"
        f"{text}"
    )

    raw = picoclaw_adapter.chat_sync(prompt)
    payload = _extract_json_payload(raw) or {}
    spoken = str(payload.get("spoken") or "").strip()
    thought = str(payload.get("thought") or "").strip()
    did_work = bool(payload.get("did_work", False))

    if not spoken:
        spoken = raw.strip() or "i'm here, but i don't have a clean reply yet."
        if not thought:
            thought = "agent returned an unstructured reply"

    return {
        "operator_text": text,
        "spoken": spoken,
        "thought": thought,
        "did_work": did_work,
        "raw": raw,
    }


_DISPATCH: dict[str, Callable[[dict[str, Any]], str]] = {
    "todo_add": _tool_todo_add,
    "set_mode": _tool_set_mode,
    "get_status": _tool_get_status,
    "see": _tool_see,
    "ask_agent": _tool_ask_agent,
    "write_doc": _tool_write_doc,
    "append_doc": _tool_append_doc,
    "write_doc_template": _tool_write_doc_template,
    "list_docs": _tool_list_docs,
    "read_doc": _tool_read_doc,
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
