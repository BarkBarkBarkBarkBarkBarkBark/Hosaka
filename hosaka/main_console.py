from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Iterable

APP_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DOC = APP_ROOT / "docs" / "no_wrong_way_manifest.md"
DEFAULT_HELP_TOPICS = (
    "/help",
    "/status",
    "/setup",
    "/network",
    "/theme",
    "/preview",
    "/manifest",
    "read <file>",
    "/exit",
)


def _print_banner() -> None:
    print("HOSAKA MAIN CONSOLE // NO WRONG WAY")
    print("Type /help to begin, /manifest for the field guide.\n")


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


def _resolve_read_target(argument: str) -> Path:
    cleaned = argument.strip()
    if cleaned in {"manifest", "guide", "manual"}:
        return MANIFEST_DOC
    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = (APP_ROOT / candidate).resolve()
    return candidate


def _read_file(argument: str) -> None:
    target = _resolve_read_target(argument)
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


def run_main_console() -> None:
    _print_banner()
    while True:
        try:
            raw = input("hosaka> ").strip()
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
        elif raw == "/preview":
            print("Preview mode is reserved for future OpenClaw integration.")
        elif raw == "/manifest":
            _read_file("manifest")
        elif raw.startswith("read "):
            _read_file(raw[5:])
        elif raw == "/exit":
            break
        else:
            try:
                proc = subprocess.run(shlex.split(raw), capture_output=True, text=True)
                if proc.stdout:
                    print(proc.stdout)
                if proc.stderr:
                    print(proc.stderr)
                if proc.returncode != 0:
                    _unknown_command(raw)
            except Exception as exc:  # noqa: BLE001
                print(f"Command failed: {exc}")
                _unknown_command(raw)
