"""The installed PlayStation catalog/launcher shared by the menu and agent."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger("hosaka.games")


def play_home() -> Path:
    home = Path.home()
    if home == Path("/root") and Path("/home/operator").is_dir():
        return Path("/home/operator")
    return home


def play_argv(*args: str) -> list[str]:
    local = play_home() / "bin" / "play"
    executable = os.getenv("HOSAKA_PLAY", "").strip() or (str(local) if local.is_file() else shutil.which("play")) or str(local)
    return [executable, "--json", *args]


def play_env() -> dict[str, str]:
    env = os.environ.copy()
    home = play_home()
    env["HOME"] = str(home)
    env["PLAY_FOREGROUND"] = "0"
    env["PATH"] = os.pathsep.join([str(home / "bin"), env.get("PATH") or os.defpath])
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", str(home / ".Xauthority"))
    return env


def run_play(*args: str, wait_s: float = 15.0) -> dict[str, Any]:
    argv = play_argv(*args)
    if not Path(argv[0]).is_file() and shutil.which(argv[0]) is None:
        error = f"play not found ({argv[0]}); install the deck's PlayStation catalog launcher"
        log.error(error)
        return {"ok": False, "error": error}
    # The system web service may run as root; games belong to the graphical operator.
    if os.geteuid() == 0 and play_home() != Path.home():
        runuser = shutil.which("runuser")
        if runuser is None:
            error = "runuser is required to launch games as operator"
            log.error(error)
            return {"ok": False, "error": error}
        argv = [runuser, "-u", "operator", "--", *argv]
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True, env=play_env(),
        )
    except OSError as exc:
        log.exception("play could not start")
        return {"ok": False, "error": f"play failed ({exc})"}
    try:
        stdout, stderr = proc.communicate(timeout=wait_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        error = f"play timed out after {wait_s:g}s; launch was not confirmed"
        log.error(error)
        return {"ok": False, "error": error}
    try:
        payload = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        error = (stderr or stdout).strip()[:400] or f"play returned no catalog response (exit {proc.returncode})"
        log.error("Invalid play response: %s", error)
        return {"ok": False, "error": error}
    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        log.error("play returned an invalid result")
        return {"ok": False, "error": "play returned an invalid result"}
    if proc.returncode != 0 and payload["ok"]:
        error = stderr.strip()[:400] or f"play exited with status {proc.returncode}; success was not confirmed"
        log.error(error)
        return {"ok": False, "error": error}
    if not payload["ok"]:
        log.error("play rejected command: %s", payload.get("error") or payload.get("message") or payload.get("action"))
    return payload
