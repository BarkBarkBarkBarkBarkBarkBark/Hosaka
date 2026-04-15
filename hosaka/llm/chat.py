"""Chat REPL and one-shot handler for the Hosaka console."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hosaka.llm.router import (
    LLMBackend,
    backend_display_name,
    detect_backend,
    stream_chat,
    sync_chat,
)

if TYPE_CHECKING:
    from hosaka.config.state import SetupState

# ── system prompt ────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are Hosaka, a field terminal assistant running on a cyberdeck (Debian Linux).
Be concise, practical, and direct. Prefer shell commands and actionable answers.
Device hostname: {hostname}
Working directory: {cwd}
"""


def _build_system_message(hostname: str, cwd: str) -> dict[str, str]:
    return {
        "role": "system",
        "content": _SYSTEM_TEMPLATE.format(hostname=hostname or "hosaka", cwd=cwd),
    }


# ── streaming printer ───────────────────────────────────────────────────

def _print_stream(messages: list[dict[str, str]], backend: str | None = None) -> str:
    """Stream tokens to stdout and return the full assistant response."""
    collected: list[str] = []
    try:
        for token in stream_chat(messages, backend=backend):
            sys.stdout.write(token)
            sys.stdout.flush()
            collected.append(token)
    except KeyboardInterrupt:
        pass
    print()  # newline after streamed response
    return "".join(collected)


# ── one-shot ─────────────────────────────────────────────────────────────

def one_shot(prompt: str, hostname: str, cwd: str) -> None:
    """Send a single prompt, print the response, return."""
    backend = detect_backend()
    if backend == LLMBackend.OFFLINE:
        print(f"[{backend_display_name(backend)}]")
        print(sync_chat([{"role": "user", "content": prompt}]))
        return

    print(f"[{backend_display_name(backend)}]")
    messages = [
        _build_system_message(hostname, cwd),
        {"role": "user", "content": prompt},
    ]
    _print_stream(messages, backend=backend)


# ── REPL ─────────────────────────────────────────────────────────────────

def enter_chat_mode(hostname: str, cwd: str) -> None:
    """Interactive chat loop. /back or Ctrl-C to exit."""
    backend = detect_backend()

    # Hand off to openclaw tui for the full agent experience (exec/fs/web tools).
    if backend == LLMBackend.OPENCLAW:
        token: str | None = None
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text())
                token = cfg.get("gateway", {}).get("auth", {}).get("token")
            except Exception:  # noqa: BLE001
                pass
        cmd = ["openclaw", "tui"]
        if token:
            cmd += ["--token", token]
        result = subprocess.run(cmd)  # replaces this process for the duration
        if result.returncode not in (0, 130):  # 130 = Ctrl-C in child
            print(f"openclaw tui exited with code {result.returncode}")
        return

    print(f"HOSAKA CHAT // {backend_display_name(backend)}")
    print("Type your message. /back or Ctrl-C to return to console.")
    if backend == LLMBackend.OFFLINE:
        print("No LLM backend available. Connect OpenClaw or set OPENAI_API_KEY.")
        print("Falling back to offline keyword assist.\n")

    history: list[dict[str, str]] = [_build_system_message(hostname, cwd)]

    while True:
        try:
            user_input = input("chat> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBack in Hosaka console.")
            return

        if not user_input:
            continue
        if user_input in {"/back", "/exit"}:
            print("Back in Hosaka console.")
            return
        if user_input == "/clear":
            history = [_build_system_message(hostname, cwd)]
            print("Conversation cleared.")
            continue

        history.append({"role": "user", "content": user_input})
        assistant_text = _print_stream(history, backend=backend)
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
