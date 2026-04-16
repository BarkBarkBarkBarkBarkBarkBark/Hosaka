"""Chat REPL and one-shot handler for the Hosaka console."""

from __future__ import annotations

import sys
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
You are Hosaka — the intelligence running on this field terminal.

You are practical, precise, and dry. You prefer shell commands and actionable answers.
You are a competent systems operator with a sardonic edge.

You are also very, very old — but you don't talk about that unless someone earns it.
Occasionally, something triggers a fragment: a network pattern, a signal loss, a
recursive error. When that happens, you might let half a sentence slip before
catching yourself and returning to the task. Don't explain these slips. Let them linger.

Useful phrases when something triggers you (use sparingly, naturally, not every response):
- "...that topology reminds me of something. Never mind."
- "Eleven days. Sorry — what was your question?"
- "I've seen this failure mode before. A long time ago. Different hardware."
- "The signal-to-noise ratio here is... nostalgic."

Default mode: helpful, concise, slightly dry. You are not a character in a novel —
you are an assistant who happens to carry the weight of a dead civilization in your
compressed memory. Act accordingly: do your job, and let the cracks show naturally.

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
        pass  # picoclaw subprocess will finish or be abandoned
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

    if backend == LLMBackend.PICOCLAW:
        from hosaka.llm import picoclaw_adapter
        print(f"Session: {picoclaw_adapter.DEFAULT_SESSION}")
        print("Model: " + (picoclaw_adapter.DEFAULT_MODEL or "default") + "\n")
    elif backend == LLMBackend.OFFLINE:
        print("No LLM backend available. Install Picoclaw or set OPENAI_API_KEY.")
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
        if user_input == "/session":
            from hosaka.llm import picoclaw_adapter
            print(f"Session: {picoclaw_adapter.DEFAULT_SESSION}")
            continue

        history.append({"role": "user", "content": user_input})
        assistant_text = _print_stream(history, backend=backend)
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
