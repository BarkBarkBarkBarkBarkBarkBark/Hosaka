"""Hosaka diagnostics API.

Shared, read-only diagnostic surface for the SPA, /device page, and CLI.
Collectors are intentionally best-effort: every section should return useful
status even when platform tools such as nmcli, pactl, v4l2-ctl, or bluetoothctl
are missing.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from hosaka.web.api_v1 import (
    BOOT_MARKER,
    KEY_SERVICES,
    _cpu_temp,
    _listening_ports,
    _mem,
    _net,
    _read_mode,
    _services,
    _uptime_seconds,
    _urls,
    require_auth,
)

router = APIRouter(prefix="/api/v1/diag", tags=["diagnostics"])

MAX_TEXT = 12000


def _run(cmd: list[str], timeout: int = 5) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "available": True,
            "cmd": cmd,
            "rc": proc.returncode,
            "stdout": proc.stdout[:MAX_TEXT],
            "stderr": proc.stderr[:2000],
        }
    except FileNotFoundError:
        return {"available": False, "cmd": cmd, "rc": 127, "stdout": "", "stderr": f"not found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"available": True, "cmd": cmd, "rc": 124, "stdout": "", "stderr": f"timeout: {' '.join(cmd)}"}
    except OSError as exc:
        return {"available": False, "cmd": cmd, "rc": 1, "stdout": "", "stderr": str(exc)}


def _tool(name: str) -> bool:
    return shutil.which(name) is not None


def _split_lines(text: str, limit: int = 80) -> list[str]:
    return [line.rstrip() for line in text.splitlines()[:limit] if line.strip()]


def _df() -> list[dict[str, str]]:
    result = _run(["df", "-hP"], timeout=5)
    rows: list[dict[str, str]] = []
    if result["rc"] != 0:
        return rows
    for line in result["stdout"].splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) == 6:
            rows.append({
                "filesystem": parts[0],
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_percent": parts[4],
                "mount": parts[5],
            })
    return rows[:24]


def _interfaces() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sys_net = Path("/sys/class/net")
    if sys_net.exists():
        for iface in sorted(sys_net.iterdir()):
            name = iface.name
            out.append({
                "name": name,
                "state": (iface / "operstate").read_text(encoding="utf-8").strip() if (iface / "operstate").exists() else None,
                "mac": (iface / "address").read_text(encoding="utf-8").strip() if (iface / "address").exists() else None,
                "wireless": (iface / "wireless").exists(),
            })
        return out
    result = _run(["ifconfig"], timeout=5)
    if result["rc"] == 0:
        for line in result["stdout"].splitlines():
            if line and not line.startswith(("\t", " ")) and ":" in line:
                out.append({"name": line.split(":", 1)[0], "state": None, "mac": None, "wireless": False})
    return out


def _network_diag() -> dict[str, Any]:
    net = _net()
    nmcli_devices = _run(["nmcli", "-t", "-e", "no", "device", "status"], timeout=5) if _tool("nmcli") else {"available": False}
    wifi = _run(["nmcli", "-t", "-e", "no", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no"], timeout=6) if _tool("nmcli") else {"available": False}
    return {
        "primary": net.model_dump() if hasattr(net, "model_dump") else net.dict(),
        "interfaces": _interfaces(),
        "listening_ports": _listening_ports(),
        "urls": _urls(net),
        "nmcli_available": bool(nmcli_devices.get("available")),
        "nmcli_devices": _split_lines(str(nmcli_devices.get("stdout", ""))),
        "wifi_visible": _split_lines(str(wifi.get("stdout", "")), limit=30),
        "tailscale_available": _tool("tailscale"),
    }


def _audio_diag() -> dict[str, Any]:
    pactl_sources: list[str] = []
    pactl_sinks: list[str] = []
    alsa_inputs: list[str] = []
    alsa_outputs: list[str] = []
    system_audio: list[str] = []
    if _tool("pactl"):
        pactl_sources = _split_lines(_run(["pactl", "list", "short", "sources"], timeout=5).get("stdout", ""))
        pactl_sinks = _split_lines(_run(["pactl", "list", "short", "sinks"], timeout=5).get("stdout", ""))
    if _tool("arecord"):
        alsa_inputs = _split_lines(_run(["arecord", "-l"], timeout=5).get("stdout", ""))
    if _tool("aplay"):
        alsa_outputs = _split_lines(_run(["aplay", "-l"], timeout=5).get("stdout", ""))
    if platform.system() == "Darwin" and _tool("system_profiler"):
        system_audio = _split_lines(_run(["system_profiler", "SPAudioDataType"], timeout=8).get("stdout", ""), limit=80)
    return {
        "available": bool(pactl_sources or pactl_sinks or alsa_inputs or alsa_outputs or system_audio),
        "browser_can_enumerate": True,
        "tools": {"pactl": _tool("pactl"), "arecord": _tool("arecord"), "aplay": _tool("aplay")},
        "inputs": pactl_sources or alsa_inputs,
        "outputs": pactl_sinks or alsa_outputs,
        "system_audio": system_audio,
        "note": "Browser mic/speaker labels require permission; use the diagnostics app for live meter testing.",
    }


def _video_diag() -> dict[str, Any]:
    devices: list[dict[str, str]] = []
    for path in sorted(Path("/dev").glob("video*")):
        devices.append({"path": str(path), "kind": "v4l2"})
    v4l2 = _run(["v4l2-ctl", "--list-devices"], timeout=5) if _tool("v4l2-ctl") else {"available": False, "stdout": ""}
    system_cameras: list[str] = []
    if platform.system() == "Darwin" and _tool("system_profiler"):
        system_cameras = _split_lines(_run(["system_profiler", "SPCameraDataType"], timeout=8).get("stdout", ""), limit=80)
    return {
        "available": bool(devices or v4l2.get("stdout") or system_cameras),
        "browser_can_preview": True,
        "devices": devices,
        "v4l2": _split_lines(str(v4l2.get("stdout", "")), limit=80),
        "system_cameras": system_cameras,
        "snapshot_url": "/api/v1/voice/camera/snapshot.jpg",
        "note": "Use the diagnostics app for an in-browser live preview; server snapshot uses the configured local camera path.",
    }


def _usb_diag() -> dict[str, Any]:
    if _tool("lsusb"):
        lines = _split_lines(_run(["lsusb"], timeout=5).get("stdout", ""), limit=80)
        return {"available": bool(lines), "tool": "lsusb", "devices": lines}
    if platform.system() == "Darwin" and _tool("system_profiler"):
        lines = _split_lines(_run(["system_profiler", "SPUSBDataType"], timeout=10).get("stdout", ""), limit=120)
        return {"available": bool(lines), "tool": "system_profiler", "devices": lines}
    return {"available": False, "tool": None, "devices": [], "note": "install lsusb/usbutils for deeper USB inventory"}


def _bluetooth_diag() -> dict[str, Any]:
    if _tool("bluetoothctl"):
        show = _split_lines(_run(["bluetoothctl", "show"], timeout=5).get("stdout", ""), limit=60)
        devices = _split_lines(_run(["bluetoothctl", "devices"], timeout=5).get("stdout", ""), limit=80)
        return {"available": bool(show or devices), "tool": "bluetoothctl", "controller": show, "devices": devices}
    if platform.system() == "Darwin" and _tool("system_profiler"):
        lines = _split_lines(_run(["system_profiler", "SPBluetoothDataType"], timeout=10).get("stdout", ""), limit=120)
        return {"available": bool(lines), "tool": "system_profiler", "controller": lines, "devices": []}
    return {"available": False, "tool": None, "controller": [], "devices": []}


def _battery_diag() -> dict[str, Any]:
    supplies = []
    root = Path("/sys/class/power_supply")
    if root.exists():
        for entry in sorted(root.iterdir()):
            data: dict[str, str] = {"name": entry.name}
            for key in ("type", "status", "capacity", "voltage_now", "current_now", "model_name"):
                path = entry / key
                if path.exists():
                    try:
                        data[key] = path.read_text(encoding="utf-8").strip()
                    except OSError:
                        pass
            supplies.append(data)
    if supplies:
        return {"available": True, "supplies": supplies}
    if platform.system() == "Darwin" and _tool("pmset"):
        lines = _split_lines(_run(["pmset", "-g", "batt"], timeout=5).get("stdout", ""), limit=20)
        return {"available": bool(lines), "supplies": [{"name": "pmset", "status": "\n".join(lines)}]}
    return {"available": False, "supplies": []}


def _system_diag() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    mem = _mem()
    services = _services()
    return {
        "mode": _read_mode(),
        "boot_marker": BOOT_MARKER.exists(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "uptime_seconds": _uptime_seconds(),
        "cpu_temp_c": _cpu_temp(),
        "mem": mem.model_dump() if hasattr(mem, "model_dump") else mem.dict(),
        "disk_root": {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        },
        "mounts": _df(),
        "services": [svc.model_dump() if hasattr(svc, "model_dump") else svc.dict() for svc in services],
        "key_services": list(KEY_SERVICES),
    }


def _peripherals_diag() -> dict[str, Any]:
    return {
        "audio": _audio_diag(),
        "video": _video_diag(),
        "usb": _usb_diag(),
        "bluetooth": _bluetooth_diag(),
        "battery": _battery_diag(),
    }


def build_snapshot() -> dict[str, Any]:
    """Return the complete diagnostics bundle used by all surfaces."""
    return {
        "ok": True,
        "schema": "hosaka.diag.v1",
        "timestamp": int(time.time()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "mode": _read_mode(),
        "system": _system_diag(),
        "network": _network_diag(),
        "peripherals": _peripherals_diag(),
    }


@router.get("/system", dependencies=[Depends(require_auth)])
def diag_system() -> dict[str, Any]:
    return _system_diag()


@router.get("/network", dependencies=[Depends(require_auth)])
def diag_network() -> dict[str, Any]:
    return _network_diag()


@router.get("/peripherals", dependencies=[Depends(require_auth)])
def diag_peripherals() -> dict[str, Any]:
    return _peripherals_diag()


@router.get("/snapshot", dependencies=[Depends(require_auth)])
def diag_snapshot() -> dict[str, Any]:
    return build_snapshot()
