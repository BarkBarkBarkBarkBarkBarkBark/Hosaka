"""Portable PlayStation catalog and RetroArch launcher; no ROMs are bundled."""
from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("hosaka.play")
ROM_EXTENSIONS = (".m3u", ".cue", ".chd", ".pbp", ".iso")


def rom_root() -> Path:
    return Path(os.getenv("HOSAKA_PSX_ROMS", str(Path.home() / "RetroPie/roms/psx"))).expanduser()


def catalog() -> list[Path]:
    root = rom_root()
    if not root.is_dir():
        raise FileNotFoundError(f"PlayStation ROM folder not found: {root}. Set HOSAKA_PSX_ROMS.")
    found = sorted((p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in ROM_EXTENSIONS),
                   key=lambda p: str(p).casefold())
    best: dict[str, Path] = {}
    for path in found:
        key = path.stem.casefold()
        previous = best.get(key)
        if previous is None or ROM_EXTENSIONS.index(path.suffix.lower()) < ROM_EXTENSIONS.index(previous.suffix.lower()):
            best[key] = path
    return sorted(best.values(), key=lambda p: p.stem.casefold())


def score(query: str, path: Path) -> int:
    name, query = path.stem.casefold(), query.casefold()
    if name == query:
        return 100
    if name.startswith(query):
        return 80
    if query in name:
        return 60
    return 40 if all(word in name for word in query.split()) else 0


def launch_argv(rom: Path) -> list[str]:
    core = os.getenv("HOSAKA_PSX_CORE", "").strip()
    if core:
        if not Path(core).expanduser().is_file():
            raise FileNotFoundError(f"PlayStation libretro core not found: {core}")
        executable = os.getenv("HOSAKA_RETROARCH", "").strip() or shutil.which("retroarch")
        if not executable:
            raise FileNotFoundError("RetroArch is not installed. Set HOSAKA_RETROARCH.")
        argv = [executable, "-L", str(Path(core).expanduser())]
        config = os.getenv("HOSAKA_RETROARCH_CONFIG", "").strip()
        if config:
            if not Path(config).expanduser().is_file():
                raise FileNotFoundError(f"RetroArch configuration not found: {config}")
            argv += ["--config", str(Path(config).expanduser())]
        return [*argv, str(rom)]
    config = Path("/opt/retropie/configs/psx/emulators.cfg")
    if not config.is_file():
        raise FileNotFoundError("Set HOSAKA_PSX_CORE to an installed PS1 libretro core (or install RetroPie).")
    entries: dict[str, str] = {}
    for line in config.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            entries[key.strip()] = value.strip().strip('"')
    command = entries.get(entries.get("default", ""), "")
    argv = shlex.split(command)
    if not argv or "%ROM%" not in argv or "-L" not in argv:
        raise ValueError("Unsupported RetroPie PS1 command; set HOSAKA_PSX_CORE for direct RetroArch launch.")
    # Parse arguments rather than executing RetroPie's command through a shell.
    executable = Path(argv[0])
    if executable.name != "retroarch" or not executable.is_file():
        raise FileNotFoundError(f"RetroArch executable not found: {executable}")
    core_index = argv.index("-L") + 1
    if core_index >= len(argv) or not Path(argv[core_index]).is_file():
        raise FileNotFoundError("The RetroPie PS1 libretro core is missing.")
    return [str(rom) if arg == "%ROM%" else arg for arg in argv]


def state_file() -> Path:
    return Path(os.getenv("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "hosaka/play.json"


def process_identity(pid: int) -> str:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, timeout=3)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Could not inspect emulator process: {result.stderr.strip()}")
    return result.stdout.strip()


def stop() -> dict[str, Any]:
    state = state_file()
    if not state.exists():
        return {"ok": True, "action": "stop", "message": "No game launched by Hosaka is running."}
    saved = json.loads(state.read_text())
    if not isinstance(saved, dict):
        raise ValueError("Invalid Hosaka emulator state; refusing to signal an unknown process.")
    pid, identity = saved.get("pid"), saved.get("identity")
    if not isinstance(pid, int) or pid <= 1 or not isinstance(identity, str) or not identity:
        raise ValueError("Invalid Hosaka emulator state; refusing to signal an unknown process.")
    if process_identity(pid) != identity:
        state.unlink()
        return {"ok": True, "action": "stop", "message": "The previous Hosaka game has already exited."}
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if process_identity(pid) != identity:
            state.unlink()
            return {"ok": True, "action": "stop", "message": "Stopped the Hosaka game."}
        time.sleep(0.1)
    raise RuntimeError("RetroArch did not exit after the stop request; its game is still running.")


def graphical_env() -> dict[str, str]:
    env = os.environ.copy()
    if sys.platform.startswith("linux"):
        runtime = Path(f"/run/user/{os.getuid()}")
        if runtime.is_dir():
            env.setdefault("XDG_RUNTIME_DIR", str(runtime))
            if (runtime / "bus").exists():
                env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime / 'bus'}")
        if not env.get("DISPLAY"):
            for number in (0, 1, 2):
                if Path(f"/tmp/.X11-unix/X{number}").exists():
                    env["DISPLAY"] = f":{number}"
                    break
        env.setdefault("XAUTHORITY", str(Path.home() / ".Xauthority"))
        if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
            raise RuntimeError("No graphical session is available for RetroArch.")
    return env


def other_retroarch_pids() -> list[int]:
    result = subprocess.run(["ps", "-u", str(os.getuid()), "-o", "pid=,comm="],
                            capture_output=True, text=True, timeout=3, check=True)
    pids = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and Path(parts[1]).name == "retroarch":
            pids.append(int(parts[0]))
    return pids


def signal_voice(sig: signal.Signals) -> None:
    if not sys.platform.startswith("linux"):
        return
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            args = (entry / "cmdline").read_bytes().split(b"\0")
            if any(args[index:index + 3] == [b"-m", b"hosaka", b"voice"] for index in range(len(args) - 2)):
                os.kill(int(entry.name), sig)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            log.warning("Could not pause/resume Hosaka voice: %s", exc)
        except FileNotFoundError:
            continue


def launch(rom: Path) -> dict[str, Any]:
    argv, env = launch_argv(rom), graphical_env()
    state = state_file()
    state.parent.mkdir(parents=True, exist_ok=True)
    # Stop only a verified process recorded by Hosaka, never arbitrary RetroArch instances.
    stop()
    if other_retroarch_pids():
        raise RuntimeError("RetroArch is already running outside Hosaka's launcher. Quit that game before using /play.")
    output = state.parent / "play.log"
    with output.open("ab") as stream:
        signal_voice(signal.SIGUSR1)
        try:
            proc = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=stream,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            signal_voice(signal.SIGUSR2)
            raise
    try:
        time.sleep(0.6)
        if proc.poll() is not None:
            raise RuntimeError(f"RetroArch exited with status {proc.returncode}; see {output}")
        identity = process_identity(proc.pid)
        if not identity:
            raise RuntimeError(f"RetroArch exited before launch confirmation; see {output}")
        state.write_text(json.dumps({"pid": proc.pid, "identity": identity, "title": rom.stem}) + "\n")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
        finally:
            signal_voice(signal.SIGUSR2)
        raise
    return {"ok": True, "action": "launch", "system": "psx", "title": rom.stem, "pid": proc.pid}


def execute(args: list[str]) -> dict[str, Any]:
    if args and args[0] in {"--help", "-h"}:
        return {"ok": True, "action": "help", "message": "hosaka play [list [psx]|stop|game name]"}
    if args == ["stop"]:
        result = stop()
        signal_voice(signal.SIGUSR2)
        return result
    if not args or args in (["list"], ["list", "psx"], ["list", "ps1"]):
        return {"ok": True, "action": "list", "system": "psx",
                "games": [{"system": "psx", "title": path.stem} for path in catalog()]}
    if args[0] == "list":
        raise ValueError("Hosaka's native library is PlayStation 1; use hosaka play list psx.")
    query = " ".join(args).strip()
    if not query or len(query) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in query):
        raise ValueError("Use a game name of 1-256 characters without control characters.")
    ranked = [(score(query, path), path) for path in catalog()]
    ranked = sorted((item for item in ranked if item[0] > 0), key=lambda item: -item[0])
    if not ranked:
        raise ValueError(f"No game matches {query!r}. Use /play list psx.")
    matches = [path for value, path in ranked if value == ranked[0][0]]
    if len(matches) != 1:
        return {"ok": False, "action": "ambiguous", "query": query,
                "matches": [{"system": "psx", "title": path.stem} for path in matches]}
    return launch(matches[0])


def render(payload: dict[str, Any]) -> None:
    if payload.get("action") == "ambiguous":
        print("Several matches; use /play with one of these exact titles:")
        for match in payload["matches"]:
            print(f"  {match['title']}")
    elif not payload["ok"]:
        print(payload["error"])
    elif payload["action"] == "list":
        print(f"{len(payload['games'])} PlayStation games:")
        for game in payload["games"]:
            print(f"  {game['title']}")
    elif payload["action"] == "launch":
        print(f"Launching {payload['title']} through RetroArch.")
    else:
        print(payload.get("message", ""))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in args
    if json_mode:
        args.remove("--json")
    try:
        payload = execute(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        log.error("Play failed: %s", exc)
        payload = {"ok": False, "error": str(exc)}
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        render(payload)
    return 0 if payload["ok"] else 2 if payload.get("action") == "ambiguous" else 1


if __name__ == "__main__":
    raise SystemExit(main())
