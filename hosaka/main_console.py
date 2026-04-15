from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Iterable

from hosaka.llm.chat import enter_chat_mode, one_shot
from hosaka.ops.updater import run_update

APP_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DOC = APP_ROOT / "docs" / "no_wrong_way_manifest.md"
DEFAULT_HELP_TOPICS = (
    "/help",
    "/status",
    "/setup",
    "/network",
    "/theme",
    "/manifest",
    "update",
    "read <file>",
    "code",
    "chat",
    "chat <prompt>",
    "/openclaw status",
    "/openclaw doctor",
    "/openclaw install",
    "/exit",
)


def _print_banner() -> None:
    print("HOSAKA MAIN CONSOLE // NO WRONG WAY")
    print("Type /help to begin. chat to talk to the LLM. code for a shell.\n")


def _show_help() -> None:
    print("No Wrong Way — command guide")
    print("You can use slash commands or system shell commands.")
    print("Core commands:")
    for topic in DEFAULT_HELP_TOPICS:
        print(f"  - {topic}")
    print("\nTip: `read manifest` opens the built-in operator manual.")


def _show_manifest_hint() -> None:
    print("Try: read manifest")


def _paginate_lines(lines: Iterable[str], page_size: int = 24) -> None:
    chunk: list[str] = []
    for line in lines:
        chunk.append(line.rstrip("\n"))
        if len(chunk) == page_size:
            for item in chunk:
                print(item)
            chunk.clear()
            user = input("--More-- [Enter=next, q=quit] ").strip().lower()
            if user == "q":
                print("Exited reader.")
                return
    for item in chunk:
        print(item)
    print("\n[end of file] Type Enter to continue.")
    input()


def _resolve_read_target(argument: str, current_dir: Path) -> Path:
    cleaned = argument.strip()
    if cleaned in {"manifest", "guide", "manual"}:
        return MANIFEST_DOC
    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = (current_dir / candidate).resolve()
    return candidate


def _read_file(argument: str, current_dir: Path) -> None:
    target = _resolve_read_target(argument, current_dir=current_dir)
    if not target.exists():
        print(f"Read failed: file not found: {target}")
        return
    if target.is_dir():
        print(f"Read failed: {target} is a directory.")
        return
    print(f"Reading: {target}")
    print("Press q when prompted to exit early.\n")
    with target.open("r", encoding="utf-8", errors="replace") as handle:
        numbered = (f"{idx:04d} | {line}" for idx, line in enumerate(handle, start=1))
        _paginate_lines(numbered)


def _unknown_command(command: str) -> None:
    print(f"`{command}` is not a known command yet — and that's okay.")
    print("No Wrong Way: I can redirect you.")
    print("Try one of:")
    for topic in DEFAULT_HELP_TOPICS:
        print(f"  - {topic}")
    _show_manifest_hint()


def _run_update_flow() -> None:
    print("Starting Hosaka update... this may restart services.")
    ok, output = run_update()
    print(output)
    if ok:
        print("Update complete.")
    else:
        print("Update encountered an issue.")


def _change_directory(argument: str, current_dir: Path) -> Path:
    target_input = argument.strip() or "~"
    candidate = Path(target_input).expanduser()
    if not candidate.is_absolute():
        candidate = (current_dir / candidate).resolve()
    if not candidate.exists():
        print(f"cd failed: path does not exist: {candidate}")
        return current_dir
    if not candidate.is_dir():
        print(f"cd failed: not a directory: {candidate}")
        return current_dir
    return candidate


def _enter_code_mode(current_dir: Path) -> None:
    shell = os.environ.get("SHELL", "/bin/bash")
    print(f"Entering shell ({shell}). Type 'exit' or Ctrl-D to return.")
    try:
        subprocess.run([shell], cwd=str(current_dir))  # noqa: S603
    except Exception as exc:  # noqa: BLE001
        print(f"Shell failed: {exc}")
    print("Back in Hosaka console.")


def _hostname() -> str:
    """Best-effort hostname from state file or system."""
    try:
        from hosaka.config.state import StateStore

        state = StateStore().load()
        if state.hostname:
            return state.hostname
    except Exception:  # noqa: BLE001
        pass
    import socket

    return socket.gethostname()


def _openclaw_status() -> None:
    from hosaka.llm.openclaw import (
        configured_model,
        is_cli_installed,
        is_gateway_up,
        OPENCLAW_GATEWAY_PORT,
    )

    cli = is_cli_installed()
    gateway = is_gateway_up()
    status = "gateway online" if gateway else ("CLI installed" if cli else "not installed")
    print(f"OpenClaw: {status}")
    print(f"Gateway:  127.0.0.1:{OPENCLAW_GATEWAY_PORT}")
    print(f"Model:    {configured_model()}")
    if not gateway:
        print("Run /openclaw install to set up, or /openclaw doctor for diagnostics.")


def _openclaw_doctor() -> None:
    from hosaka.llm.openclaw import doctor

    print("Running OpenClaw diagnostics...\n")
    info = doctor()
    print(f"  CLI installed:         {info['cli_installed']}")
    print(f"  CLI version:           {info['cli_version'] or 'n/a'}")
    print(f"  Gateway up (:{info['gateway_port']}):  {info['gateway_up']}")
    print(f"  Configured model:      {info['configured_model']}")
    print(f"  OpenAI key set:        {info['openai_key_set']}")
    print(f"  Config exists:         {info['config_exists']}")
    print()
    if not info['cli_installed']:
        print("Fix: run /openclaw install")
    elif not info['openai_key_set']:
        print("Fix: set OPENAI_API_KEY in your .env file")
    elif not info['config_exists']:
        print("Fix: run /openclaw install to complete onboarding")
    elif not info['gateway_up']:
        print("Fix: restart Hosaka or run 'openclaw gateway start'")
    else:
        print("All checks passed. Type 'chat' to start talking.")


def _openclaw_install() -> None:
    from hosaka.llm.openclaw import run_install_script

    print("Running OpenClaw installer...")
    print("This will install Node.js 24 and the openclaw CLI, then onboard with OpenAI.")
    print("Requires OPENAI_API_KEY to be set in your environment.\n")
    ok, output = run_install_script()
    if output:
        print(output)
    if ok:
        print("\nOpenClaw install complete. Type 'chat' to start talking.")
    else:
        print("\nOpenClaw install encountered an issue. Run /openclaw doctor for details.")


def run_main_console() -> None:
    _print_banner()
    current_dir = Path.cwd()
    while True:
        try:
            raw = input(f"hosaka:{current_dir} > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting Hosaka console.")
            break

        if not raw:
            continue
        if raw == "/help":
            _show_help()
        elif raw == "/status":
            print("System online. Setup complete. No Wrong Way mode active.")
        elif raw == "/setup":
            print("Setup is managed by the onboarding orchestrator and web UI.")
        elif raw == "/theme":
            print("Theme command stub. Use setup flow or web GUI to change it.")
        elif raw == "/network":
            print("Use setup step or web network page to inspect network details.")
        elif raw == "/openclaw status" or raw == "/openclaw":
            _openclaw_status()
        elif raw == "/openclaw doctor":
            _openclaw_doctor()
        elif raw == "/openclaw install":
            _openclaw_install()
        elif raw == "/manifest":
            _read_file("manifest", current_dir=current_dir)
        elif raw in {"update", "/update"}:
            _run_update_flow()
        elif raw.startswith("read "):
            _read_file(raw[5:], current_dir=current_dir)
        elif raw == "code":
            _enter_code_mode(current_dir)
        elif raw == "chat":
            enter_chat_mode(hostname=_hostname(), cwd=str(current_dir))
        elif raw.startswith("chat "):
            one_shot(raw[5:], hostname=_hostname(), cwd=str(current_dir))
        elif raw == "pwd":
            print(current_dir)
        elif raw == "cd" or raw.startswith("cd "):
            current_dir = _change_directory(raw[2:].strip(), current_dir=current_dir)
            print(f"Directory: {current_dir}")
        elif raw == "/exit":
            break
        else:
            try:
                proc = subprocess.run(shlex.split(raw), capture_output=True, text=True, cwd=str(current_dir))
                if proc.stdout:
                    print(proc.stdout)
                if proc.stderr:
                    print(proc.stderr)
                if proc.returncode != 0:
                    _unknown_command(raw)
            except Exception as exc:  # noqa: BLE001
                print(f"Command failed: {exc}")
                _unknown_command(raw)
