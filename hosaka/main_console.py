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
    "/manifest",
    "update",
    "read <file>",
    "code",
    "chat",
    "!<shell command>",
    "/picoclaw status",
    "/picoclaw doctor",
    "/exit",
)


def _print_banner() -> None:
    print("HOSAKA MAIN CONSOLE // NO WRONG WAY")
    print("Just type — everything goes to Picoclaw. Use !cmd for shell. /help for commands.\n")


def _show_help() -> None:
    print("No Wrong Way — command guide")
    print("Anything you type goes to the Picoclaw agent unless it's a known command.")
    print("Prefix with ! to run a shell command directly (e.g. !ls -la).")
    print("\nBuilt-in commands:")
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


def _picoclaw_status() -> None:
    import shutil
    from hosaka.llm import picoclaw_adapter

    installed = bool(shutil.which("picoclaw"))
    print(f"Picoclaw: {'installed' if installed else 'NOT FOUND on PATH'}")
    print(f"Session:  {picoclaw_adapter.DEFAULT_SESSION}")
    print(f"Model:    {picoclaw_adapter.DEFAULT_MODEL or 'default'}")
    if not installed:
        print("Install: https://github.com/sipeed/picoclaw/releases")
    else:
        print("Run 'picoclaw gateway' to start the daemon if not already running.")


def _picoclaw_doctor() -> None:
    import json, shutil
    from pathlib import Path
    from hosaka.llm import picoclaw_adapter

    installed = bool(shutil.which("picoclaw"))
    cfg_path = Path.home() / ".picoclaw" / "config.json"
    cfg_ok = cfg_path.exists()

    print(f"  Installed:        {installed}")
    print(f"  Config exists:    {cfg_ok}")

    if cfg_ok:
        cfg = json.loads(cfg_path.read_text())
        d = cfg.get("agents", {}).get("defaults", {})
        print(f"  Workspace:        {d.get('workspace', 'n/a')}")
        print(f"  Restricted:       {d.get('restrict_to_workspace', True)}")
        gw = cfg.get("gateway", {})
        print(f"  Gateway:          {gw.get('host','127.0.0.1')}:{gw.get('port', 18790)}")
        print(f"  Model:            {d.get('model_name', 'n/a')}")
    print(f"  Session key:      {picoclaw_adapter.DEFAULT_SESSION}")
    print()
    if not installed:
        print("Fix: install picoclaw from https://github.com/sipeed/picoclaw/releases")
    elif not cfg_ok:
        print("Fix: run 'picoclaw onboard' to initialise config")
    else:
        print("All checks passed. Type anything to chat.")


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
        elif raw in {"/status", "/setup", "/network", "/theme"}:
            print("System online. Type anything to chat, or /help for commands.")
        elif raw in {"/picoclaw", "/picoclaw status"}:
            _picoclaw_status()
        elif raw == "/picoclaw doctor":
            _picoclaw_doctor()
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
        elif raw.startswith("!"):
            # Explicit shell passthrough: !ls -la
            shell_cmd = raw[1:].strip()
            try:
                proc = subprocess.run(
                    shell_cmd, shell=True, text=True, cwd=str(current_dir)  # noqa: S602
                )
                if proc.returncode != 0:
                    print(f"[exit {proc.returncode}]")
            except Exception as exc:  # noqa: BLE001
                print(f"Shell error: {exc}")
        else:
            # Everything else → Picoclaw agent (one-shot)
            one_shot(raw, hostname=_hostname(), cwd=str(current_dir))
