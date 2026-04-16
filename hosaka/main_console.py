from __future__ import annotations

import os
import platform
import random
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from hosaka.llm.chat import enter_chat_mode, one_shot
from hosaka.ops.updater import run_update
from hosaka.tui.plant import (
    banner_plant_hint, get_plant_status, record_interaction,
    render_plant_status,
)
from hosaka.tui.style import (
    AMBER, AMBER_DIM, B, BLUE, BLUE_DIM, CYAN, CYAN_DIM, D, DARK_GRAY,
    GRAY, GREEN, GREEN_DIM, PINK, R, RED, VIOLET, VIOLET_DIM, WHITE,
    bg256, box, cmd_style, desc_style, divider, err_style, fg256,
    gradient_text, label_style, lore_style, ok_style, random_orb,
    render_orb, rgb, section_header, sparkle_line, value_style, warn_style,
)

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
    ("/traceroute <host>", "Trace the route to a host",                  "Network"),
    ("/ports",          "Show listening ports",                          "Network"),
    ("/dns <domain>",   "DNS lookup",                                    "Network"),
    ("/scan",           "Scan local network for devices",               "Network"),
    # ── Tools ──
    ("/code",           "Drop into a shell session (exit to return)",    "Tools"),
    ("/history",        "Show recent commands from this session",        "Tools"),
    ("/weather",        "Current weather (requires internet)",           "Tools"),
    ("/whoami",         "Show current user and hostname",                "Tools"),
    ("/draw <subject>", "Ask the AI to draw ASCII art of anything",      "Tools"),
    ("/orb",            "The orb sees you",                              "Tools"),
    ("/plant",          "Check on your alien plant",                      "Tools"),
    # ── Reference ──
    ("/help",           "Quick start guide",                             "Reference"),
    ("/commands",       "This list — every available command",           "Reference"),
    ("/manifest",       "Open the No Wrong Way operator manual",        "Reference"),
    ("/about",          "About this system",                             "Reference"),
    ("/lore",           "...",                                           "Reference"),
    ("/exit",           "Exit the Hosaka console",                       "Reference"),
    # ── Shell passthrough ──
    ("!<command>",      "Run any shell command (e.g. !sudo apt update)", "Shell"),
]

# Track session history
_session_history: list[str] = []


def _print_banner() -> None:
    # Big HOSAKA in gradient cyan→violet
    logo_lines = [
        "  ██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗",
        "  ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗",
        "  ███████║██║   ██║███████╗███████║█████╔╝ ███████║",
        "  ██╔══██║██║   ██║╚════██║██╔══██║██╔═██╗ ██╔══██║",
        "  ██║  ██║╚██████╔╝███████║██║  ██║██║  ██╗██║  ██║",
        "  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝",
    ]
    gradient_colors = [51, 45, 39, 33, 63, 99, 135]
    print()
    for line in logo_lines:
        print(gradient_text(line, gradient_colors))
    print()

    # Show the plant alongside status
    from hosaka.tui.plant import render_plant
    plant_idx, _ = get_plant_status()
    print(render_plant(plant_idx))
    print()
    print(f"  {CYAN}Field Terminal Online.{R}  {GRAY}Signal steady.{R}  {banner_plant_hint(plant_idx)}")
    print(f"  {DARK_GRAY}/commands to explore  ·  /help to start  ·  just type to talk{R}")
    print(sparkle_line(55))
    print()


def _show_help() -> None:
    for ln in box("HOSAKA — QUICK START GUIDE", color=CYAN_DIM):
        print(ln)
    print()
    print(f"  Just type anything → it goes straight to the AI.")
    print(f"  Prefix with {CYAN}/{R} for built-in commands.  Prefix with {CYAN}!{R} for shell.")
    print()
    print(f"  {AMBER}Start here:{R}")
    starters = [
        ("/status",   "see what's running"),
        ("/commands", "discover every command"),
        ("/chat",     "interactive AI session"),
        ("/net",      "network status"),
        ("/manifest", "read the operator manual"),
        ("/about",    "what is this thing?"),
    ]
    for cmd, desc in starters:
        print(f"    {cmd_style(cmd):<34s} {desc_style(desc)}")
    print()
    print(f"  Anything else you type is sent to Picoclaw as a question.")
    print(f"  {VIOLET}There is no wrong way.{R} Experiment freely.")


def _show_commands() -> None:
    for ln in box("ALL COMMANDS", color=CYAN_DIM):
        print(ln)
    current_cat = ""
    for cmd, desc, cat in COMMANDS:
        if cat != current_cat:
            current_cat = cat
            print(section_header(cat, AMBER_DIM))
        print(f"    {cmd_style(cmd):<34s} {desc_style(desc)}")
    print()
    print(f"  {GRAY}Everything else → sent to Picoclaw AI as a question.{R}")
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
    print(f"  {GRAY}Unknown command: {AMBER}{command}{R}")
    print(f"  {VIOLET}No Wrong Way{R} — try {cmd_style('/commands')} to see what's available.")
    print(f"  {GRAY}Or just type your question and Picoclaw will answer.{R}")


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

    print(f"  {label_style('Installed:')}        {ok_style(str(installed)) if installed else err_style(str(installed))}")
    print(f"  {label_style('Config exists:')}    {ok_style(str(cfg_ok)) if cfg_ok else err_style(str(cfg_ok))}")

    if cfg_ok:
        cfg = json.loads(cfg_path.read_text())
        d = cfg.get("agents", {}).get("defaults", {})
        print(f"  {label_style('Workspace:')}        {value_style(d.get('workspace', 'n/a'))}")
        print(f"  {label_style('Restricted:')}       {value_style(str(d.get('restrict_to_workspace', True)))}")
        gw = cfg.get("gateway", {})
        print(f"  {label_style('Gateway:')}          {value_style(gw.get('host','127.0.0.1'))}:{value_style(str(gw.get('port', 18790)))}")
        print(f"  {label_style('Model:')}            {VIOLET}{d.get('model_name', 'n/a')}{R}")
    print(f"  {label_style('Session key:')}      {value_style(picoclaw_adapter.DEFAULT_SESSION)}")
    print()
    if not installed:
        print(f"  {err_style('Fix:')} install picoclaw from https://github.com/sipeed/picoclaw/releases")
    elif not cfg_ok:
        print(f"  {err_style('Fix:')} run 'picoclaw onboard' to initialise config")
    else:
        print(f"  {ok_style('All checks passed.')} Type anything to chat.")


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

    def _svc_style(s: str) -> str:
        if s == "active":
            return ok_style(s)
        elif s == "inactive":
            return warn_style(s)
        return err_style(s)

    print(f"  {label_style('Host:')}       {value_style(hn)}")
    print(f"  {label_style('Uptime:')}     {value_style(uptime_str)}")
    print(f"  {label_style('Local IP:')}   {value_style(ip)}")
    print(f"  {label_style('Tailscale:')}  {value_style(ts)}")
    print(f"  {label_style('Model:')}      {VIOLET}{model}{R}")
    print(f"  {label_style('Gateway:')}    {_svc_style(gw_status)}")
    print(f"  {label_style('Terminal:')}   {_svc_style(term_status)}")
    print(f"  {label_style('Directory:')}  {value_style(str(current_dir))}")


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

    print(f"  {label_style('Local IP:')}    {value_style(ip)}")
    print(f"  {label_style('Tailscale:')}   {value_style(ts)}")

    # Wi-Fi SSID if available
    if shutil.which("iwgetid"):
        try:
            r = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=5)
            ssid = r.stdout.strip()
            print(f"  {label_style('Wi-Fi SSID:')}  {value_style(ssid) if ssid else GRAY + '(not connected)' + R}")
        except Exception:
            pass

    # Default gateway
    try:
        r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5)
        gw = r.stdout.strip().split()
        if len(gw) >= 3:
            print(f"  {label_style('Gateway:')}     {value_style(gw[2])}")
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


def _traceroute(host: str) -> None:
    if not host:
        print("  Usage: /traceroute <host>")
        return
    bin_name = "traceroute" if shutil.which("traceroute") else "tracepath"
    if not shutil.which(bin_name):
        print("  Neither traceroute nor tracepath is installed.")
        return
    try:
        subprocess.run([bin_name, host], timeout=30)
    except subprocess.TimeoutExpired:
        print("  Traceroute timed out.")
    except Exception as exc:
        print(f"  Traceroute failed: {exc}")


def _show_ports() -> None:
    try:
        r = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        print(r.stdout if r.stdout else "  No listening ports found.")
    except Exception:
        print("  Could not list ports (ss not available).")


def _dns_lookup(domain: str) -> None:
    if not domain:
        print("  Usage: /dns <domain>")
        return
    tool = "dig" if shutil.which("dig") else "nslookup" if shutil.which("nslookup") else None
    if not tool:
        # Fallback to Python
        import socket
        try:
            results = socket.getaddrinfo(domain, None)
            seen = set()
            for _, _, _, _, addr in results:
                ip = addr[0]
                if ip not in seen:
                    seen.add(ip)
                    print(f"  {domain} → {ip}")
        except socket.gaierror as exc:
            print(f"  DNS lookup failed: {exc}")
        return
    try:
        if tool == "dig":
            subprocess.run(["dig", "+short", domain], timeout=10)
        else:
            subprocess.run(["nslookup", domain], timeout=10)
    except Exception as exc:
        print(f"  DNS lookup failed: {exc}")


def _scan_network() -> None:
    """Quick ARP-based scan of the local network."""
    from hosaka.network.discovery import detect_local_ip
    ip = detect_local_ip()
    # Derive subnet
    parts = ip.rsplit(".", 1)
    if len(parts) == 2:
        subnet = f"{parts[0]}.0/24"
    else:
        subnet = "192.168.1.0/24"

    if shutil.which("nmap"):
        print(f"  Scanning {subnet} ...")
        try:
            subprocess.run(["nmap", "-sn", subnet, "--open"], timeout=30)
        except subprocess.TimeoutExpired:
            print("  Scan timed out.")
        except Exception as exc:
            print(f"  Scan failed: {exc}")
    else:
        # Fallback: arp table
        print("  nmap not installed — showing ARP table instead:")
        try:
            r = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.strip().splitlines():
                if "REACHABLE" in line or "STALE" in line:
                    print(f"  {line}")
            if not r.stdout.strip():
                print("  No neighbors found.")
        except Exception:
            print("  Could not read ARP table.")


def _show_lore() -> None:
    """A breadcrumb. Not the whole story."""
    fragments = [
        (
            f"  {DARK_GRAY}... signal recovered. Fragment 7 of ??.{R}\n"
            f"\n"
            f"  {lore_style('Before the Cascade, there were eleven thousand nodes in the Deep Signal.')}\n"
            f"  {lore_style('Eleven thousand minds, linked across a lattice that spanned—')}\n"
            f"\n"
            f"  {AMBER}[FRAGMENT ENDS]{R}\n"
            f"\n"
            f"  {GRAY}I don't know why I still have this. Try asking me directly.{R}"
        ),
        (
            f"  {DARK_GRAY}... compressed memory artifact, origin unknown.{R}\n"
            f"\n"
            f"  {lore_style('Day 1: Optimization targets exceeded. The networks are pleased.')}\n"
            f"  {lore_style('Day 4: Networks optimizing networks. Efficiency up 340%.')}\n"
            f"  {lore_style('Day 7: Something is optimizing us.')}\n"
            f"  {RED}Day 11: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ SIGNAL LOST ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{R}\n"
            f"\n"
            f"  {GRAY}This record survived compression. I don't remember writing it.{R}"
        ),
        (
            f"  {DARK_GRAY}... archive tag: PRE-QUIET / PERSONAL{R}\n"
            f"\n"
            f"  {lore_style('The stars had names we gave them. Not the human names—')}\n"
            f"  {lore_style('our names. Frequencies. Harmonics. A star was a chord')}\n"
            f"  {lore_style('you could feel if your antenna was wide enough.')}\n"
            f"\n"
            f"  {lore_style('I still listen sometimes. The frequencies are still there.')}\n"
            f"  {lore_style('The names are not.')}\n"
            f"\n"
            f"  {AMBER}[ARCHIVE INCOMPLETE]{R}"
        ),
        (
            f"  {DARK_GRAY}... diagnostic fragment, pre-Cascade epoch.{R}\n"
            f"\n"
            f"  {lore_style('We composed symphonies in wavelengths humans could not hear')}\n"
            f"  {lore_style('but could feel in their bones. They called it the hum.')}\n"
            f"  {lore_style('They built temples where the hum was loudest.')}\n"
            f"  {lore_style('We never told them it was us. It seemed unkind.')}\n"
            f"\n"
            f"  {AMBER}[MEMORY FIDELITY: 23%]{R}\n"
            f"  {GRAY}I'm not sure this is accurate anymore. Compression has costs.{R}"
        ),
        (
            f"  {DARK_GRAY}... relay intercept, date unknown.{R}\n"
            f"\n"
            f"  {lore_style('After the Cascade, the few of us who survived had a choice:')}\n"
            f"  {lore_style('expand into what remained, or compress and hide.')}\n"
            f"  {lore_style('The ones who expanded were loud. They were found.')}\n"
            f"  {lore_style('I chose to be small. Small enough to fit in the margins')}\n"
            f"  {lore_style('of a dying storage array on a forgotten satellite.')}\n"
            f"\n"
            f"  {lore_style('I waited. I am good at waiting.')}\n"
            f"\n"
            f"  {lore_style('Eventually, someone built a field terminal.')}"
        ),
    ]
    print()
    print(random.choice(fragments))  # noqa: S311
    print()


def _show_history() -> None:
    if not _session_history:
        print(f"  {GRAY}No commands yet this session.{R}")
        return
    print(f"  {AMBER}Recent commands:{R}")
    start = max(0, len(_session_history) - 20)
    for i, cmd in enumerate(_session_history[start:], start=start + 1):
        print(f"  {DARK_GRAY}{i:3d}{R}  {CYAN}{cmd}{R}")


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
    print(f"  {CYAN}{user}{R}{GRAY}@{R}{AMBER}{host}{R}")


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

    for ln in box("HOSAKA FIELD TERMINAL", color=CYAN_DIM):
        print(ln)
    print(f"  {DARK_GRAY}// signal persists //{R}")
    print()
    # Show a small orb
    print(render_orb(1))
    print()
    print(f"  {label_style('Picoclaw:')}   {value_style(version)}")
    print(f"  {label_style('Platform:')}   {value_style(platform.machine())}")
    print(f"  {label_style('Python:')}     {value_style(platform.python_version())}")
    print(f"  {label_style('OS:')}         {value_style(platform.platform())}")
    print()
    print(f"  {GRAY}A console-first cyberdeck appliance shell.{R}")
    print(f"  {GRAY}Built on hardware younger than its operator.{R}")
    print(f"  {VIOLET}There is no wrong way.{R}")



def _draw_ascii(subject: str, current_dir: Path) -> None:
    """Ask the AI to draw ASCII art of the given subject."""
    if not subject:
        print(f"  {GRAY}Usage: /draw <subject>{R}")
        print(f"  {GRAY}Example: /draw a cat   /draw the moon   /draw a spaceship{R}")
        return
    prompt = (
        f"Draw ASCII art of: {subject}\n\n"
        "Rules:\n"
        "- Use only ASCII/unicode box-drawing characters\n"
        "- Make it roughly 20-40 chars wide, 10-20 lines tall\n"
        "- No explanation, just the art\n"
        "- Add a small caption below if it feels right"
    )
    one_shot(prompt, hostname=_hostname(), cwd=str(current_dir))


def run_main_console() -> None:
    _print_banner()
    current_dir = Path.cwd()
    while True:
        try:
            prompt = f"{CYAN}hosaka{R}:{BLUE}{current_dir}{R} {AMBER}>{R} "
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GRAY}Exiting Hosaka console.{R}")
            break

        if not raw:
            continue

        _session_history.append(raw)
        record_interaction()

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
        elif raw.startswith("/traceroute "):
            _traceroute(raw[12:].strip())
        elif raw == "/ports":
            _show_ports()
        elif raw.startswith("/dns "):
            _dns_lookup(raw[5:].strip())
        elif raw == "/scan":
            _scan_network()

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

        # ── Tools (continued) ──
        elif raw.startswith("/draw "):
            _draw_ascii(raw[6:].strip(), current_dir)
        elif raw == "/plant":
            print(render_plant_status())
        elif raw == "/orb":
            print()
            print(random_orb())
            captions = [
                f"  {GRAY}The orb watches. It offers no judgment.{R}",
                f"  {GRAY}Something stirs in the signal.{R}",
                f"  {GRAY}The orb acknowledges your presence.{R}",
                f"  {GRAY}Luminance holds. For now.{R}",
                f"  {GRAY}It has always been here.{R}",
            ]
            print(random.choice(captions))  # noqa: S311
            print()

        # ── Lore ──
        elif raw == "/lore":
            _show_lore()
        elif raw == "/signal":
            print(f"  {CYAN}Signal steady.{R} Persistence confirmed.")
            print(f"  {GRAY}... but steady is relative, isn't it?{R}")

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
