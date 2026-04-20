"""Hosaka v1 API — single source of truth for remote clients.

This is the public, versioned surface that `hosakactl` (the Mac client),
the `/device` page in the kiosk, and any third-party tool talk to.

Design rules (kept deliberately small for a Pi 3B + maintainability):

* Stdlib + `nmcli` + `systemctl` only — no extra Python deps.
* Every endpoint returns a typed Pydantic model so OpenAPI is rich enough
  to drive auto-generated docs (mkdocs-material plugin reads /openapi.json).
* Auth: `Authorization: Bearer <token>` where the token lives at
  `/etc/hosaka/api-token` (or `$HOSAKA_API_TOKEN`). Loopback (127.0.0.1) is
  always allowed without a token so the local kiosk SPA / TTY dashboard work.
* Side-effects are funneled through the `hosaka` CLI on the box, not
  reimplemented here. That keeps one source of truth for "what does
  switching modes mean".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from hosaka.ops.updater import APP_ROOT, UPDATE_SCRIPT
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# ── config ────────────────────────────────────────────────────────────────────

TOKEN_FILE = Path(os.getenv("HOSAKA_API_TOKEN_FILE", "/etc/hosaka/api-token"))
RUNTIME_MODE_FILE = Path(os.getenv("HOSAKA_MODE_FILE", "/var/lib/hosaka/mode"))
BOOT_MARKER = Path("/boot/firmware/hosaka-build-mode")
HOSAKA_CLI = os.getenv("HOSAKA_CLI", "/usr/local/bin/hosaka")

KEY_SERVICES = (
    "hosaka-webserver.service",
    "picoclaw-gateway.service",
    "hosaka-mode.service",
    "hosaka-device-dashboard.service",
    "ssh.service",
)

# ── auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def _load_token() -> Optional[str]:
    env = os.getenv("HOSAKA_API_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_FILE.exists():
        try:
            tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
            return tok or None
        except OSError:
            return None
    return None


def _is_loopback(req: Request) -> bool:
    client = req.client
    if not client:
        return False
    host = client.host or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def require_auth(
    req: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """Allow if loopback, OR bearer matches stored token, OR no token configured."""
    if _is_loopback(req):
        return
    expected = _load_token()
    if not expected:
        # No token configured → API is read-only-from-LAN by default. We still
        # block writes via per-endpoint dependency `require_write` below.
        return
    if creds and creds.scheme.lower() == "bearer" and creds.credentials == expected:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid bearer token")


def require_write(
    req: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """Stricter: writes require either loopback or a real bearer match."""
    if _is_loopback(req):
        return
    expected = _load_token()
    if not expected:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "no API token configured on this Pi — generate one at /etc/hosaka/api-token",
        )
    if creds and creds.scheme.lower() == "bearer" and creds.credentials == expected:
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid bearer token")


# ── shell helpers ─────────────────────────────────────────────────────────────


def _run(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout: {' '.join(cmd)}"


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ── models ────────────────────────────────────────────────────────────────────

ModeName = Literal["console", "device"]


class HealthOut(BaseModel):
    web: str = "ok"
    mode: ModeName
    hostname: str
    uptime_seconds: int
    timestamp: int


class MemInfo(BaseModel):
    total_mb: int
    used_mb: int
    available_mb: int
    swap_used_mb: int


class NetInfo(BaseModel):
    ip: Optional[str] = None
    iface: Optional[str] = None
    ssid: Optional[str] = None
    mac: Optional[str] = None
    tailscale_ip: Optional[str] = None


class ServiceInfo(BaseModel):
    name: str
    active: bool
    sub: str
    enabled: bool


class SystemInfoOut(BaseModel):
    mode: ModeName
    boot_marker: bool
    hostname: str
    uptime_seconds: int
    cpu_temp_c: Optional[float] = None
    mem: MemInfo
    net: NetInfo
    services: list[ServiceInfo]
    urls: dict[str, str]
    listening_ports: list[int]


class ModeOut(BaseModel):
    mode: ModeName
    boot_marker: bool


class ModeIn(BaseModel):
    mode: ModeName
    persist: bool = False


class WifiNetwork(BaseModel):
    ssid: str
    saved: bool = False
    in_range: bool = False
    signal: Optional[int] = Field(None, description="0–100 from nmcli")
    security: Optional[str] = None
    active: bool = False


class WifiList(BaseModel):
    networks: list[WifiNetwork]


class WifiAdd(BaseModel):
    ssid: str = Field(..., min_length=1, max_length=64)
    psk: Optional[str] = Field(None, min_length=8, max_length=128, description="omit for open networks")
    hidden: bool = False


class ActionResult(BaseModel):
    ok: bool
    message: str = ""


# ── system info collectors ────────────────────────────────────────────────────


def _read_mode() -> ModeName:
    raw = _read_file(str(RUNTIME_MODE_FILE))
    if raw == "device" or raw == "build":
        return "device"
    if raw == "console" or raw == "kiosk":
        return "console"
    return "device" if BOOT_MARKER.exists() else "console"


def _uptime_seconds() -> int:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except OSError:
        return 0


def _cpu_temp() -> Optional[float]:
    raw = _read_file("/sys/class/thermal/thermal_zone0/temp")
    if not raw:
        return None
    try:
        return round(int(raw) / 1000.0, 1)
    except ValueError:
        return None


def _mem() -> MemInfo:
    info: dict[str, int] = {}
    for line in _read_file("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        v = v.strip().split()[0]
        try:
            info[k] = int(v)  # KiB
        except ValueError:
            pass
    total = info.get("MemTotal", 0) // 1024
    avail = info.get("MemAvailable", 0) // 1024
    swap_total = info.get("SwapTotal", 0) // 1024
    swap_free = info.get("SwapFree", 0) // 1024
    return MemInfo(
        total_mb=total,
        used_mb=max(total - avail, 0),
        available_mb=avail,
        swap_used_mb=max(swap_total - swap_free, 0),
    )


def _net() -> NetInfo:
    iface = ip = mac = ssid = ts = None
    rc, out, _ = _run(["ip", "-4", "route", "show", "default"])
    if rc == 0 and out.strip():
        parts = out.split()
        if "dev" in parts:
            iface = parts[parts.index("dev") + 1]
    if iface:
        rc, out, _ = _run(["ip", "-4", "-o", "addr", "show", "dev", iface])
        if rc == 0:
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
            if m:
                ip = m.group(1)
        mac_path = f"/sys/class/net/{iface}/address"
        if Path(mac_path).exists():
            mac = _read_file(mac_path) or None
    if shutil.which("iwgetid"):
        rc, out, _ = _run(["iwgetid", "-r"])
        if rc == 0 and out.strip():
            ssid = out.strip()
    if shutil.which("tailscale"):
        rc, out, _ = _run(["tailscale", "ip", "-4"], timeout=3)
        if rc == 0 and out.strip():
            ts = out.strip().splitlines()[0]
    return NetInfo(ip=ip, iface=iface, ssid=ssid, mac=mac, tailscale_ip=ts)


def _services() -> list[ServiceInfo]:
    out: list[ServiceInfo] = []
    for name in KEY_SERVICES:
        rc1, a, _ = _run(["systemctl", "is-active", name], timeout=4)
        rc2, e, _ = _run(["systemctl", "is-enabled", name], timeout=4)
        rc3, s, _ = _run(["systemctl", "show", name, "-p", "SubState", "--value"], timeout=4)
        out.append(
            ServiceInfo(
                name=name,
                active=a.strip() == "active",
                sub=(s.strip() or "unknown"),
                enabled=e.strip() in {"enabled", "static", "alias"},
            )
        )
    return out


def _listening_ports() -> list[int]:
    rc, out, _ = _run(["ss", "-tlnH"], timeout=4)
    ports: set[int] = set()
    if rc == 0:
        for line in out.splitlines():
            cols = line.split()
            if len(cols) < 4:
                continue
            addr = cols[3]
            m = re.search(r":(\d+)$", addr)
            if m:
                p = int(m.group(1))
                if 0 < p < 65535:
                    ports.add(p)
    return sorted(ports)


def _urls(net: NetInfo) -> dict[str, str]:
    host = net.ip or net.tailscale_ip or "127.0.0.1"
    base = f"http://{host}:8421"
    return {
        "ui": base,
        "device": f"{base}/device",
        "setup": f"{base}/setup/",
        "api": f"{base}/api/v1",
        "openapi": f"{base}/openapi.json",
    }


# ── router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Liveness ping",
    dependencies=[Depends(require_auth)],
)
def v1_health() -> HealthOut:
    return HealthOut(
        mode=_read_mode(),
        hostname=socket.gethostname(),
        uptime_seconds=_uptime_seconds(),
        timestamp=int(time.time()),
    )


@router.get(
    "/system/info",
    response_model=SystemInfoOut,
    summary="One-shot snapshot of everything device-mode shows",
    dependencies=[Depends(require_auth)],
)
def v1_system_info() -> SystemInfoOut:
    net = _net()
    return SystemInfoOut(
        mode=_read_mode(),
        boot_marker=BOOT_MARKER.exists(),
        hostname=socket.gethostname(),
        uptime_seconds=_uptime_seconds(),
        cpu_temp_c=_cpu_temp(),
        mem=_mem(),
        net=net,
        services=_services(),
        urls=_urls(net),
        listening_ports=_listening_ports(),
    )


@router.get(
    "/mode",
    response_model=ModeOut,
    summary="Get current operating mode",
    dependencies=[Depends(require_auth)],
)
def v1_mode_get() -> ModeOut:
    return ModeOut(mode=_read_mode(), boot_marker=BOOT_MARKER.exists())


@router.post(
    "/mode",
    response_model=ModeOut,
    summary="Switch operating mode (console|device)",
    dependencies=[Depends(require_write)],
)
def v1_mode_set(body: ModeIn) -> ModeOut:
    if not Path(HOSAKA_CLI).exists():
        raise HTTPException(500, f"{HOSAKA_CLI} not installed")
    args = [HOSAKA_CLI, "mode", body.mode]
    if body.persist:
        args.append("--persist")
    # Run detached so we don't kill ourselves if the mode switch restarts the
    # webserver; the caller polls /mode to confirm. 4 s should be enough for
    # the CLI to write the runtime mode file before we read it back.
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    return ModeOut(mode=_read_mode(), boot_marker=BOOT_MARKER.exists())


# ── wifi (NetworkManager) ─────────────────────────────────────────────────────


def _nmcli(*args: str, timeout: int = 12) -> tuple[int, str, str]:
    return _run(["nmcli", "-t", "-e", "no", *args], timeout=timeout)


@router.get(
    "/wifi/networks",
    response_model=WifiList,
    summary="Saved + visible wifi networks (nmcli)",
    dependencies=[Depends(require_auth)],
)
def v1_wifi_list() -> WifiList:
    if not shutil.which("nmcli"):
        raise HTTPException(501, "nmcli not installed")
    saved: dict[str, dict[str, Any]] = {}
    rc, out, _ = _nmcli("-f", "NAME,TYPE", "connection", "show")
    if rc == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "802-11-wireless":
                saved[parts[0]] = {"saved": True}
    visible: dict[str, dict[str, Any]] = {}
    rc, out, _ = _nmcli(
        "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no"
    )
    if rc == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            in_use, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
            if not ssid:
                continue
            try:
                sig = int(signal)
            except ValueError:
                sig = None
            visible[ssid] = {
                "in_range": True,
                "signal": sig,
                "security": security or None,
                "active": in_use.strip() == "*",
            }
    keys = set(saved) | set(visible)
    nets = [
        WifiNetwork(
            ssid=k,
            saved=k in saved,
            in_range=visible.get(k, {}).get("in_range", False),
            signal=visible.get(k, {}).get("signal"),
            security=visible.get(k, {}).get("security"),
            active=visible.get(k, {}).get("active", False),
        )
        for k in sorted(keys, key=lambda s: (-(visible.get(s, {}).get("signal") or 0), s))
    ]
    return WifiList(networks=nets)


@router.post(
    "/wifi/networks",
    response_model=ActionResult,
    summary="Add or join a wifi network",
    dependencies=[Depends(require_write)],
)
def v1_wifi_add(body: WifiAdd) -> ActionResult:
    if not shutil.which("nmcli"):
        raise HTTPException(501, "nmcli not installed")
    args = ["device", "wifi", "connect", body.ssid]
    if body.psk:
        args += ["password", body.psk]
    if body.hidden:
        args += ["hidden", "yes"]
    rc, out, err = _run(["nmcli", *args], timeout=45)
    if rc != 0:
        return ActionResult(ok=False, message=(err or out).strip()[:400])
    return ActionResult(ok=True, message=out.strip()[:400] or f"connected to {body.ssid}")


@router.delete(
    "/wifi/networks/{ssid}",
    response_model=ActionResult,
    summary="Forget a saved wifi network",
    dependencies=[Depends(require_write)],
)
def v1_wifi_forget(ssid: str) -> ActionResult:
    if not shutil.which("nmcli"):
        raise HTTPException(501, "nmcli not installed")
    rc, out, err = _run(["nmcli", "connection", "delete", ssid], timeout=10)
    if rc != 0:
        return ActionResult(ok=False, message=(err or out).strip()[:400])
    return ActionResult(ok=True, message=f"forgot {ssid}")


# ── services ──────────────────────────────────────────────────────────────────


@router.get(
    "/services",
    response_model=list[ServiceInfo],
    summary="Status of the Hosaka systemd units",
    dependencies=[Depends(require_auth)],
)
def v1_services() -> list[ServiceInfo]:
    return _services()


@router.post(
    "/services/{name}/restart",
    response_model=ActionResult,
    summary="Restart one of the known Hosaka units",
    dependencies=[Depends(require_write)],
)
def v1_service_restart(name: str) -> ActionResult:
    if name not in KEY_SERVICES:
        raise HTTPException(404, f"unknown service: {name}")
    rc, _, err = _run(["sudo", "-n", "systemctl", "restart", name], timeout=15)
    if rc != 0:
        return ActionResult(ok=False, message=err.strip()[:400] or f"rc={rc}")
    return ActionResult(ok=True, message=f"restarted {name}")


@router.post(
    "/system/update",
    response_model=ActionResult,
    summary="Run the Hosaka git pull / reinstall script in the background",
    dependencies=[Depends(require_write)],
)
def v1_system_update() -> ActionResult:
    """Same flow as the Python TUI `/update` — fires `scripts/update_hosaka.sh`.

    Runs detached so the HTTP handler returns before services restart.
    """
    if not UPDATE_SCRIPT.exists():
        return ActionResult(
            ok=False,
            message=f"update script not found: {UPDATE_SCRIPT}",
        )
    try:
        subprocess.Popen(
            [str(UPDATE_SCRIPT)],
            cwd=str(APP_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return ActionResult(ok=False, message=str(exc)[:400])
    return ActionResult(
        ok=True,
        message="update started — services may restart; check ssh or journalctl",
    )
