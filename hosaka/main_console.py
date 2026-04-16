from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from hosaka.llm.chat import enter_chat_mode, one_shot
from hosaka.ops.updater import run_update

APP_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DOC = APP_ROOT / "docs" / "no_wrong_way_manifest.md"

# ── command registry ─────────────────────────────────────────────────────
# Each entry: (command, short description, [category])

COMMANDS: list[tuple[str, str, str]] = [
    # ── Chat & AI ──
    ("/chat",           "Enter interactive chat mode with the AI",       "Chat & AI"),
    ("/chat <text>",    "One-shot question — ask and get an answer",     "Chat & AI"),
    ("/ask <text>",     "Alias for /chat <text>",                        "Chat & AI"),
    # ── System ──
    ("/status",         "System overview — uptime, IP, model, services", "System"),
    ("/doctor",         "Diagnose picoclaw config and connectivity",     "System"),
    ("/restart terminal", "Restart the Hosaka terminal service",         "System"),
    ("/restart gateway",  "Restart the picoclaw gateway service",        "System"),
    ("/restart all",    "Restart both terminal and gateway",             "System"),
    ("/update",         "Pull latest code, reinstall, restart services", "System"),
    ("/uptime",         "Show system uptime",                            "System"),
    # ── Files & Navigation ──
    ("/read <file>",    "Paginate a file (also: /read manifest)",       "Files & Navigation"),
    ("/cd <path>",      "Change working directory",                      "Files & Navigation"),
    ("/pwd",            "Print working directory",                       "Files & Navigation"),
    ("/ls [path]",      "List directory contents",                       "Files & Navigation"),
    ("/tree [path]",    "Show directory tree (2 levels deep)",           "Files & Navigation"),
    # ── Network ──
    ("/net",            "Show IP addresses, Wi-Fi, and Tailscale status","Network"),
    ("/ping <host>",    "Ping a host",                                   "Network"),
    # ── Tools ──
    ("/code",           "Drop into a shell session (exit to return)",    "Tools"),
    ("/history",        "Show recent commands from this session",        "Tools"),
    ("/weather",        "Current weather (requires internet)",           "Tools"),
    ("/whoami",         "Show current user and hostname",                "Tools"),
    # ── Reference ──
    ("/help",           "Quick start guide",                             "Reference"),
    ("/commands",       "This list — every available command",           "Reference"),
    ("/manifest",       "Open the No Wrong Way operator manual",        "Reference"),
    ("/about",          "About this system",                             "Reference"),
    ("/exit",           "Exit the Hosaka console",                       "Reference"),
    # ── Shell passthrough ──
    ("!<command>",      "Run any shell command (e.g. !sudo apt update)", "Shell"),
]

# Track session history
_session_history: list[str] = []


def _print_banner() -> None:
    print("HOSAKA MAIN CONSOLE // NO WRONG WAY")
    print("Just type — everything goes to Picoclaw.  /commands to explore.  /help to start.\n")


def _show_help() -> None:
    print("┌─────────────────────────────────────┐")
    print("│     HOSAKA — QUICK START GUIDE       │")
    print("└─────────────────────────────────────┘")
    print()
    print("  Just type anything → it goes straight to the AI.")
    print("  Prefix with / for built-in commands.  Prefix with ! for shell.")
    print()
    print("  Start here:")
    print("    /status          — see what's running")
    print("    /commands        — discover every command")
    print("    /chat            — interactive AI session")
    print("    /net             — network status")
    print("    /manifest        — read the operator manual")
    print("    /about           — what is this thing?")
    print()
    print("  Anything else you type is sent to Picoclaw as a question.")
    print("  There is no wrong way. Experiment freely.")


def _show_commands() -> None:
    print("┌─────────────────────────────────────┐")
    print("│     ALL COMMANDS                     │")
    print("└─────────────────────────────────────┘")
    current_cat = ""
    for cmd, desc, cat in COMMANDS:
        if cat != current_cat:
            current_cat = cat
            print(f"\n  ── {cat} ──")
        print(f"    {cmd:<22s} {desc}")
    print()
    print("  Everything else → sent to Picoclaw AI as a question.")
    print()


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
    print(f"  Unknown command: {command}")
    print("  No Wrong Way — try /commands to see what's available.")
    print("  Or just type your question and Picoclaw will answer.")


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


# ── new commands ─────────────────────────────────────────────────────────

def _show_status(current_dir: Path) -> None:
    """Compact system overview."""
    from hosaka.llm import picoclaw_adapter
    from hosaka.network.discovery import detect_local_ip, detect_tailscale_status
    import json

    ip = detect_local_ip()
    ts = detect_tailscale_status()
    hn = _hostname()
    model = "unknown"
    cfg_path = Path.home() / ".picoclaw" / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            model = cfg.get("agents", {}).get("defaults", {}).get("model_name", "unknown")
        except Exception:
            pass

    # Service status
    def _svc(name: str) -> str:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", name],
                capture_output=True, text=True, timeout=5,
            )
            return r.stdout.strip()
        except Exception:
            return "unknown"

    gw_status = _svc("picoclaw-gateway.service")
    term_status = _svc("hosaka-field-terminal.service")

    # Uptime
    try:
        up = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
        uptime_str = up.stdout.strip()
    except Exception:
        uptime_str = "unknown"

    print(f"  Host:       {hn}")
    print(f"  Uptime:     {uptime_str}")
    print(f"  Local IP:   {ip}")
    print(f"  Tailscale:  {ts}")
    print(f"  Model:      {model}")
    print(f"  Gateway:    {gw_status}")
    print(f"  Terminal:   {term_status}")
    print(f"  Directory:  {current_dir}")


def _restart_service(target: str) -> None:
    """Restart a systemd service by short name."""
    service_map = {
        "terminal": "hosaka-field-terminal.service",
        "gateway": "picoclaw-gateway.service",
    }

    if target == "all":
        targets = ["picoclaw-gateway.service", "hosaka-field-terminal.service"]
    elif target in service_map:
        targets = [service_map[target]]
    else:
        print(f"  Unknown service: {target}")
        print("  Usage: /restart terminal | /restart gateway | /restart all")
        return

    for svc in targets:
        short = svc.split(".")[0].replace("picoclaw-", "").replace("hosaka-field-", "")
        print(f"  Restarting {short}...")
        try:
            proc = subprocess.run(
                ["sudo", "systemctl", "restart", svc],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode == 0:
                print(f"  {short}: restarted")
            else:
                print(f"  {short}: failed — {proc.stderr.strip()}")
        except Exception as exc:
            print(f"  {short}: error — {exc}")


def _show_net() -> None:
    """Network summary."""
    from hosaka.network.discovery import detect_local_ip, detect_tailscale_status

    ip = detect_local_ip()
    ts = detect_tailscale_status()

    print(f"  Local IP:    {ip}")
    print(f"  Tailscale:   {ts}")

    # Wi-Fi SSID if available
    if shutil.which("iwgetid"):
        try:
            r = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=5)
            ssid = r.stdout.strip()
            print(f"  Wi-Fi SSID:  {ssid or '(not connected)'}")
        except Exception:
            pass

    # Default gateway
    try:
        r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5)
        gw = r.stdout.strip().split()
        if len(gw) >= 3:
            print(f"  Gateway:     {gw[2]}")
    except Exception:
        pass


def _ping(host: str) -> None:
    if not host:
        print("  Usage: /ping <host>")
        return
    try:
        subprocess.run(["ping", "-c", "4", host], timeout=15)
    except subprocess.TimeoutExpired:
        print("  Ping timed out.")
    except Exception as exc:
        print(f"  Ping failed: {exc}")


def _list_dir(path_str: str, current_dir: Path) -> None:
    target = Path(path_str).expanduser() if path_str else current_dir
    if not target.is_absolute():
        target = (current_dir / target).resolve()
    if not target.is_dir():
        print(f"  Not a directory: {target}")
        return
    try:
        entries = sorted(target.iterdir())
        for e in entries:
            suffix = "/" if e.is_dir() else ""
            print(f"  {e.name}{suffix}")
        if not entries:
            print("  (empty)")
    except PermissionError:
        print(f"  Permission denied: {target}")


def _tree(path_str: str, current_dir: Path) -> None:
    target = Path(path_str).expanduser() if path_str else current_dir
    if not target.is_absolute():
        target = (current_dir / target).resolve()
    try:
        subprocess.run(["tree", "-L", "2", "--dirsfirst", str(target)], timeout=10)
    except FileNotFoundError:
        # tree not installed, fallback
        _list_dir(path_str, current_dir)
    except Exception as exc:
        print(f"  Tree failed: {exc}")


def _show_history() -> None:
    if not _session_history:
        print("  No commands yet this session.")
        return
    print("  Recent commands:")
    start = max(0, len(_session_history) - 20)
    for i, cmd in enumerate(_session_history[start:], start=start + 1):
        print(f"  {i:3d}  {cmd}")


def _show_weather() -> None:
    try:
        r = subprocess.run(
            ["curl", "-s", "wttr.in/?format=3"],
            capture_output=True, text=True, timeout=10,
        )
        print(f"  {r.stdout.strip()}" if r.stdout.strip() else "  Could not fetch weather.")
    except Exception:
        print("  Could not fetch weather (no internet?).")


def _show_whoami() -> None:
    import socket
    user = os.environ.get("USER", "unknown")
    host = socket.gethostname()
    print(f"  {user}@{host}")


def _show_uptime() -> None:
    try:
        r = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
        print(f"  {r.stdout.strip()}")
    except Exception:
        print("  Could not read uptime.")


def _show_about() -> None:
    import json
    version = "unknown"
    cfg_path = Path.home() / ".picoclaw" / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            bi = cfg.get("build_info", {})
            version = bi.get("version", "unknown")
        except Exception:
            pass

    print("  ┌─────────────────────────────────────┐")
    print("  │         HOSAKA FIELD TERMINAL        │")
    print("  └─────────────────────────────────────┘")
    print(f"  Picoclaw version:  {version}")
    print(f"  Platform:          {platform.machine()}")
    print(f"  Python:            {platform.python_version()}")
    print(f"  OS:                {platform.platform()}")
    print()
    print("  A console-first cyberdeck appliance shell.")
    print("  There is no wrong way.")



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

        _session_history.append(raw)

        # ── Reference ──
        if raw == "/help":
            _show_help()
        elif raw == "/commands":
            _show_commands()
        elif raw == "/manifest":
            _read_file("manifest", current_dir=current_dir)
        elif raw == "/about":
            _show_about()

        # ── System ──
        elif raw == "/status":
            _show_status(current_dir)
        elif raw in {"/doctor", "/picoclaw doctor", "/picoclaw"}:
            _picoclaw_doctor()
        elif raw in {"/picoclaw status"}:
            _picoclaw_status()
        elif raw.startswith("/restart"):
            target = raw[len("/restart"):].strip()
            _restart_service(target or "all")
        elif raw == "/update":
            _run_update_flow()
        elif raw == "/uptime":
            _show_uptime()

        # ── Files & Navigation ──
        elif raw.startswith("/read "):
            _read_file(raw[6:], current_dir=current_dir)
        elif raw == "/pwd":
            print(f"  {current_dir}")
        elif raw == "/cd" or raw.startswith("/cd "):
            current_dir = _change_directory(raw[3:].strip(), current_dir=current_dir)
            print(f"  {current_dir}")
        elif raw == "/ls" or raw.startswith("/ls "):
            _list_dir(raw[3:].strip(), current_dir)
        elif raw == "/tree" or raw.startswith("/tree "):
            _tree(raw[5:].strip(), current_dir)

        # ── Network ──
        elif raw == "/net":
            _show_net()
        elif raw.startswith("/ping "):
            _ping(raw[6:].strip())

        # ── Tools ──
        elif raw == "/code":
            _enter_code_mode(current_dir)
        elif raw == "/history":
            _show_history()
        elif raw == "/weather":
            _show_weather()
        elif raw == "/whoami":
            _show_whoami()

        # ── Chat (explicit) ──
        elif raw == "/chat":
            enter_chat_mode(hostname=_hostname(), cwd=str(current_dir))
        elif raw.startswith("/chat "):
            one_shot(raw[6:], hostname=_hostname(), cwd=str(current_dir))
        elif raw.startswith("/ask "):
            one_shot(raw[5:], hostname=_hostname(), cwd=str(current_dir))

        # ── Exit ──
        elif raw == "/exit":
            break

        # ── Legacy compat (redirect old forms) ──
        elif raw in {"update", "/setup", "/network", "/theme"}:
            _show_status(current_dir)
        elif raw.startswith("read "):
            _read_file(raw[5:], current_dir=current_dir)
        elif raw == "code":
            _enter_code_mode(current_dir)
        elif raw == "chat":
            enter_chat_mode(hostname=_hostname(), cwd=str(current_dir))
        elif raw.startswith("chat "):
            one_shot(raw[5:], hostname=_hostname(), cwd=str(current_dir))
        elif raw == "pwd":
            print(f"  {current_dir}")
        elif raw == "cd" or raw.startswith("cd "):
            current_dir = _change_directory(raw[2:].strip(), current_dir=current_dir)
            print(f"  {current_dir}")

        # ── Shell passthrough ──
        elif raw.startswith("!"):
            shell_cmd = raw[1:].strip()
            try:
                proc = subprocess.run(
                    shell_cmd, shell=True, text=True, cwd=str(current_dir)  # noqa: S602
                )
                if proc.returncode != 0:
                    print(f"[exit {proc.returncode}]")
            except Exception as exc:  # noqa: BLE001
                print(f"Shell error: {exc}")

        # ── Unknown slash command ──
        elif raw.startswith("/"):
            _unknown_command(raw)

        # ── Default: everything else → Picoclaw ──
        else:
            one_shot(raw, hostname=_hostname(), cwd=str(current_dir))
