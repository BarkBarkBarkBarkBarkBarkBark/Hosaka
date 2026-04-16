"""Chat REPL and one-shot handler for the Hosaka console."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hosaka.llm.router import (
    LLMBackend,
    backend_display_name,
    detect_backend,
    shutdown_gateway,
    stream_chat,
    sync_chat,
    _get_gateway,
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
        # Abort active gateway run on Ctrl-C
        gw = _get_gateway()
        if gw is not None:
            try:
                gw.abort()
            except Exception:
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

    print(f"HOSAKA CHAT // {backend_display_name(backend)}")
    print("Type your message. /back or Ctrl-C to return to console.")

    if backend == LLMBackend.OPENCLAW:
        gw = _get_gateway()
        if gw is not None:
            print(f"Session: {gw.session_key}")
            print("Agent tools active. Ctrl-C aborts active generation.\n")
        else:
            print("Gateway detected but connection failed. Falling back.\n")
            backend = LLMBackend.OPENAI if __import__('hosaka.llm.openai_adapter', fromlist=['is_available']).is_available() else LLMBackend.OFFLINE
    elif backend == LLMBackend.OFFLINE:
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
            gw = _get_gateway()
            if gw is not None:
                try:
                    gw.reset_session()
                    print("Session and conversation cleared.")
                except Exception:
                    print("Conversation cleared (local).")
            else:
                print("Conversation cleared.")
            continue
        if user_input == "/session":
            gw = _get_gateway()
            if gw is not None:
                print(f"Session: {gw.session_key}")
            else:
                print("No active gateway session.")
            continue

        history.append({"role": "user", "content": user_input})
        assistant_text = _print_stream(history, backend=backend)
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
