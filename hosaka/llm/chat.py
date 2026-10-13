"""Chat REPL and one-shot handler for the Hosaka console."""

from __future__ import annotations

import logging
import math
import os
import platform
import signal
import sys
import uuid
from contextlib import closing, contextmanager
from typing import TYPE_CHECKING, Generator

from hosaka.identity import build_chat_system_prompt
from hosaka.llm import openai_adapter, picoclaw_adapter
from hosaka.llm.router import (
    LLMBackend,
    stream_chat,
)

if TYPE_CHECKING:
    from hosaka.config.state import SetupState


def _conversational_backend() -> str:
    """Console chat must stay inside the PicoClaw agent harness."""
    return LLMBackend.PICOCLAW


def _build_system_message(hostname: str, cwd: str) -> dict[str, str]:
    return {
        "role": "system",
        "content": build_chat_system_prompt(hostname=hostname, cwd=cwd, native_tools=True),
    }


# ── streaming printer ───────────────────────────────────────────────────

class _ChatDeadlineExceeded(BaseException):
    """Cancellation must bypass backend/tool handlers that catch Exception."""


@contextmanager
def _chat_deadline(seconds: float) -> Generator[None, None, None]:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("HOSAKA_CHAT_TIMEOUT must be a finite positive number.")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("Cannot start chat while another alarm timer is active.")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expire(_signum: int, _frame: object) -> None:
        raise _ChatDeadlineExceeded()

    signal.signal(signal.SIGALRM, expire)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _print_stream(
    messages: list[dict[str, str]],
    backend: str | None = None,
    session: str | None = None,
    cwd: str | None = None,
) -> str:
    """Stream tokens to stdout and return the full assistant response."""
    from hosaka.tui.style import thinking_sparkles
    collected: list[str] = []
    first = True
    spark = thinking_sparkles()
    spark.__enter__()
    try:
        with _chat_deadline(openai_adapter.REQUEST_TIMEOUT):
            if backend == LLMBackend.PICOCLAW:
                response = picoclaw_adapter.console_chat_stream(
                    messages, session=session, cwd=cwd,
                    timeout=openai_adapter.REQUEST_TIMEOUT,
                )
            else:
                from hosaka.voice.tools import chat_tool_schemas, dispatch

                response = stream_chat(
                    messages, backend=backend, session=session,
                    tools=chat_tool_schemas(), dispatch=dispatch,
                )
            with closing(response) as tokens:
                for token in tokens:
                    if not token:
                        continue
                    if first:
                        spark.stop()
                        first = False
                    sys.stdout.write(token)
                    sys.stdout.flush()
                    collected.append(token)
    except _ChatDeadlineExceeded:
        spark.stop()
        logging.getLogger("hosaka.chat").warning("Console chat deadline exceeded")
        print(
            f"\nChat timed out after {openai_adapter.REQUEST_TIMEOUT:g}s. "
            "Check your LLM connection with /doctor or /scan llm. Try again when ready."
        )
        return ""
    except KeyboardInterrupt:
        spark.stop()
        print("\nChat cancelled. Back at the prompt.")
        return ""
    except (RuntimeError, OSError, ValueError) as exc:
        spark.stop()
        logging.getLogger("hosaka.chat").warning("Console agent failed: %s", exc)
        print(
            f"\nPicoClaw chat failed: {exc}\n"
            "No direct LLM fallback was used. Check /doctor or /select llm."
        )
        return ""
    finally:
        spark.stop()
    if not collected:
        print("Chat returned no response. Check /doctor before retrying.")
        return ""
    print()  # newline after streamed response
    return "".join(collected)


# ── one-shot ─────────────────────────────────────────────────────────────

def one_shot(prompt: str, hostname: str, cwd: str) -> None:
    """Send a single prompt, print the response, return."""
    backend = _conversational_backend()
    messages = [
        _build_system_message(hostname, cwd),
        {"role": "user", "content": prompt},
    ]
    session = "hosaka:tui"
    _print_stream(messages, backend=backend, session=session, cwd=cwd)


# ── REPL ─────────────────────────────────────────────────────────────────

def enter_chat_mode(hostname: str, cwd: str, session: str = "hosaka:tui") -> None:
    """Interactive chat loop. /back or Ctrl-C to exit."""
    backend = _conversational_backend()

    print("Type your message. /back or Ctrl-C to return to console.")

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
            session = f"hosaka:tui:{uuid.uuid4().hex}"
            print("Conversation cleared.")
            continue
        if user_input == "/session":
            print(f"Session: {session}")
            continue
        if user_input == "/voice":
            try:
                from hosaka.voice.daemon import main as voice_main
            except ImportError as exc:
                print(
                    f"Voice deps not installed ({exc}). "
                    "Run scripts/install_voice_deps.sh first."
                )
                continue
            print("Entering voice mode (TUI social orb). Esc or q to return.")
            try:
                voice_main()
            except KeyboardInterrupt:
                pass
            except Exception as exc:  # noqa: BLE001
                print(f"Voice mode hit a snag: {exc}")
            try:
                from hosaka.tui.style import restore_terminal

                restore_terminal()
            except Exception:  # noqa: BLE001
                pass
            print("\nBack in Hosaka chat.")
            continue

        history.append({"role": "user", "content": user_input})
        assistant_text = _print_stream(
            history,
            backend=backend,
            session=session,
            cwd=cwd,
        )
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})


def main(argv: list[str] | None = None) -> int:
    import argparse
    from hosaka.llm.llm_config import apply_to_env, load
    from hosaka.main_console import _check_api_key

    parser = argparse.ArgumentParser(prog="hosaka")
    parser.add_argument("command", choices=["chat", "message"])
    parser.add_argument("-s", "--session", default="hosaka:main")
    parser.add_argument("-m", "--message", help="send one message instead of opening interactive chat")
    parser.add_argument("--model", help="explicit PicoClaw model alias")
    parser.add_argument("prompt", nargs="*")
    args = parser.parse_args(argv)
    if args.message is not None and args.prompt:
        parser.error("use either --message or a positional prompt")
    prompt = args.message if args.message is not None else " ".join(args.prompt)
    if args.command == "message" and not prompt.strip():
        parser.error("message requires a prompt")
    apply_to_env(load())
    if args.model:
        os.environ["PICOCLAW_MODEL"] = args.model
    _check_api_key()
    hostname, cwd = platform.node(), os.getcwd()
    if args.command == "chat" and args.message is None and not args.prompt:
        enter_chat_mode(hostname, cwd, session=args.session)
        return 0
    messages = [_build_system_message(hostname, cwd), {"role": "user", "content": prompt}]
    return 0 if _print_stream(messages, backend=_conversational_backend(), session=args.session, cwd=cwd) else 1
