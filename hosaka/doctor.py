from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = 5.0
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_WEB_HOST = "http://127.0.0.1:8421"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = Path(os.getenv("HOSAKA_STATE_DIR", "/var/lib/hosaka"))
RUNTIME_MODE_FILE = DEFAULT_STATE_DIR / "mode"
BOOT_MARKER = Path("/boot/firmware/hosaka-build-mode")
WEB_UNIT = "hosaka-webserver.service"
PICO_UNIT = "picoclaw-gateway.service"
ETC_ENV = Path("/etc/hosaka/env")
SYSTEMD_WEB_UNIT = REPO_ROOT / "systemd" / "hosaka-webserver.service"
FRONTEND_DIR = REPO_ROOT / "frontend"
UI_DIR = REPO_ROOT / "hosaka" / "web" / "ui"
CHECK_DEPS = ["idb-keyval", "@automerge/automerge"]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _run(cmd: list[str], timeout: float = DEFAULT_TIMEOUT, cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, cwd=str(cwd) if cwd else None)
    except FileNotFoundError:
        return 127, "", f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _http_json(base_url: str, path: str, token: str | None, timeout: float = DEFAULT_TIMEOUT) -> tuple[int, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "hosaka-doctor/1")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": str(exc)}


def _git_head() -> str | None:
    code, out, _ = _run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"])
    return out if code == 0 and out else None


def _git_clean() -> bool | None:
    code, _, _ = _run(["git", "-C", str(REPO_ROOT), "diff", "--quiet", "--ignore-submodules", "HEAD", "--"])
    if code in (0, 1):
        return code == 0
    return None


def _service_state(name: str) -> str | None:
    code, out, _ = _run(["systemctl", "is-active", name])
    if code == 0:
        return out or "active"
    if out:
        return out
    return None


def _read_runtime_mode() -> str | None:
    if RUNTIME_MODE_FILE.exists():
        raw = RUNTIME_MODE_FILE.read_text(encoding="utf-8").strip()
    elif BOOT_MARKER.exists():
        raw = "device"
    else:
        raw = "console"
    return {"kiosk": "console", "build": "device"}.get(raw, raw)


def _find_listeners(port: int) -> list[str]:
    if shutil.which("ss"):
        code, out, _ = _run(["ss", "-ltnH", f"sport = :{port}"])
        if code == 0 and out:
            listeners: list[str] = []
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    listeners.append(parts[3])
            return listeners
    if shutil.which("netstat"):
        code, out, _ = _run(["netstat", "-ltn"])
        if code == 0 and out:
            listeners = []
            for line in out.splitlines():
                if f":{port}" not in line:
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    listeners.append(parts[3])
            return listeners
    return []


def _host_from_url(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""


def _persistence_path_for_profile(profile: str) -> Path | None:
    if profile == "appliance":
        return DEFAULT_STATE_DIR
    if profile == "desktop":
        return Path.home() / ".hosaka" / "state"
    if profile == "docker-dev":
        return DEFAULT_STATE_DIR
    return None


def _detect_profile(explicit: str, host: str) -> str:
    if explicit != "auto":
        return explicit
    hostname = _host_from_url(host)
    if hostname and hostname not in LOCAL_HOSTS:
        return "remote"
    if SYSTEMD_WEB_UNIT.exists() and shutil.which("systemctl"):
        return "appliance"
    if Path("/.dockerenv").exists():
        return "docker-dev"
    return "desktop"


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _redact(value: Any, enabled: bool) -> Any:
    if not enabled:
        return value
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"token", "authorization", "bearer", "api_key", "api_keys"}:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact(item, enabled)
        return redacted
    if isinstance(value, list):
        return [_redact(item, enabled) for item in value]
    return value


def _check(
    *,
    slug: str,
    category: str,
    priority: str,
    status: str,
    summary: str,
    observed: Any = None,
    expected: Any = None,
    evidence: Any = None,
    remediation: str | None = None,
    source_kind: str = "derived",
) -> dict[str, Any]:
    return {
        "slug": slug,
        "category": category,
        "priority": priority,
        "status": status,
        "summary": summary,
        "observed": observed,
        "expected": expected,
        "evidence": evidence,
        "remediation": remediation,
        "source_kind": source_kind,
    }


def build_report(host: str, token: str | None, profile: str, redact: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}
    local_profile = profile in {"appliance", "desktop", "docker-dev"}

    git_head = _git_head() if REPO_ROOT.exists() else None
    git_clean = _git_clean() if REPO_ROOT.exists() else None
    runtime_mode = _read_runtime_mode() if profile == "appliance" else None
    env_file = _load_env_file(ETC_ENV) if profile == "appliance" else {}

    checks.append(_check(
        slug="doctor.surface",
        category="doctor",
        priority="p0",
        status="pass",
        summary=f"detected profile: {profile}",
        observed={"profile": profile, "host": host},
        source_kind="derived",
    ))

    if profile == "appliance":
        checks.append(_check(
            slug="runtime.mode",
            category="runtime",
            priority="p1",
            status="pass" if runtime_mode in {"console", "device"} else "warn",
            summary=f"runtime mode is {runtime_mode or 'unknown'}",
            observed=runtime_mode,
            expected="console or device",
            source_kind="host",
        ))

        web_state = _service_state(WEB_UNIT)
        checks.append(_check(
            slug="runtime.web_service",
            category="runtime",
            priority="p0",
            status="pass" if web_state == "active" else "fail",
            summary=f"{WEB_UNIT} is {web_state or 'unknown'}",
            observed=web_state,
            expected="active",
            remediation="Restart hosaka-webserver.service and inspect journalctl -u hosaka-webserver.service.",
            source_kind="host",
        ))

        pico_state = _service_state(PICO_UNIT)
        pico_expected = "inactive" if runtime_mode == "device" else "active"
        pico_status = "pass" if pico_state == pico_expected else "warn"
        pico_summary = f"{PICO_UNIT} is {pico_state or 'unknown'} (expected {pico_expected} in {runtime_mode} mode)"
        checks.append(_check(
            slug="runtime.picoclaw_service",
            category="runtime",
            priority="p2",
            status=pico_status,
            summary=pico_summary,
            observed=pico_state,
            expected=pico_expected,
            remediation="Use `hosaka mode console` to restore the interactive path, or start picoclaw-gateway.service manually if needed.",
            source_kind="host",
        ))

        kiosk_running = False
        if shutil.which("pgrep"):
            code, _, _ = _run(["pgrep", "-u", str(os.getuid()), "-f", "chromium.*hosaka-kiosk-profile"])
            kiosk_running = code == 0
        kiosk_expected = runtime_mode == "console"
        kiosk_status = "pass" if kiosk_running == kiosk_expected else "warn"
        checks.append(_check(
            slug="runtime.chromium_kiosk",
            category="runtime",
            priority="p2",
            status=kiosk_status,
            summary=f"chromium kiosk running={kiosk_running} (expected {kiosk_expected} in {runtime_mode} mode)",
            observed=kiosk_running,
            expected=kiosk_expected,
            remediation="`hosaka mode console` should relaunch Chromium; in device mode Chromium being stopped is normal.",
            source_kind="host",
        ))

        listeners = _find_listeners(8421)
        bind_kind = "unknown"
        if listeners:
            joined = " ".join(listeners)
            if "0.0.0.0:8421" in joined or "[::]:8421" in joined or "*:8421" in joined:
                bind_kind = "all-interfaces"
            elif "127.0.0.1:8421" in joined or "[::1]:8421" in joined:
                bind_kind = "loopback-only"
            else:
                bind_kind = joined
        bind_status = "pass" if bind_kind == "all-interfaces" else "warn"
        bind_remediation = None
        if bind_kind == "loopback-only":
            bind_remediation = "Set HOSAKA_WEB_HOST=0.0.0.0 in /etc/hosaka/env, then run `sudo systemctl daemon-reload && sudo systemctl restart hosaka-webserver.service` to enable Tailscale/LAN discovery."
        checks.append(_check(
            slug="network.bind_address",
            category="network",
            priority="p0",
            status=bind_status,
            summary=f"webserver bind looks like {bind_kind}",
            observed={"listeners": listeners, "env": env_file.get("HOSAKA_WEB_HOST")},
            expected="all-interfaces for tailnet discovery",
            remediation=bind_remediation,
            source_kind="host",
        ))

    if local_profile:
        ui_ok = (UI_DIR / "index.html").exists()
        checks.append(_check(
            slug="runtime.ui_build",
            category="runtime",
            priority="p1",
            status="pass" if ui_ok else "warn",
            summary=f"UI build {'present' if ui_ok else 'missing'} at {UI_DIR}",
            observed=str(UI_DIR / 'index.html'),
            expected="built UI index.html",
            remediation="Run `hosaka build` or `hosaka deploy` to refresh the SPA bundle.",
            source_kind="host",
        ))

        if FRONTEND_DIR.exists():
            nm = FRONTEND_DIR / "node_modules"
            lock = FRONTEND_DIR / "package-lock.json"
            stamp = FRONTEND_DIR / "node_modules" / ".package-lock.json"
            dep_status = "pass"
            dep_summary = "frontend dependency install looks current"
            remediation = None
            evidence: dict[str, Any] = {
                "frontend_dir": str(FRONTEND_DIR),
                "node_modules": nm.exists(),
                "package_lock": lock.exists(),
                "install_stamp": stamp.exists(),
            }
            if not nm.exists():
                dep_status = "fail"
                dep_summary = "frontend node_modules missing"
                remediation = "Run `cd frontend && npm install` or just `hosaka update` / `hosaka deploy` on the appliance CLI."
            elif lock.exists() and stamp.exists() and lock.stat().st_mtime > stamp.stat().st_mtime:
                dep_status = "warn"
                dep_summary = "frontend lockfile is newer than installed dependency stamp"
                remediation = "Run `cd frontend && npm install` to refresh synced dependencies before the next build."
            elif shutil.which("npm"):
                code, _, _ = _run(["npm", "ls", "--depth=0", *CHECK_DEPS], timeout=20, cwd=FRONTEND_DIR)
                if code != 0:
                    dep_status = "warn"
                    dep_summary = "frontend dependency check failed"
                    remediation = "Run `cd frontend && npm install` to pick up synced packages like idb-keyval or @automerge/automerge."
            checks.append(_check(
                slug="update.frontend_deps",
                category="update",
                priority="p1",
                status=dep_status,
                summary=dep_summary,
                observed=evidence,
                remediation=remediation,
                source_kind="host",
            ))

    health_code, health = _http_json(host, "/api/health", token)
    artifacts["api_health"] = health
    health_ok = health_code == 200 and isinstance(health, dict) and health.get("web") == "ok"
    checks.append(_check(
        slug="api.health",
        category="api",
        priority="p0",
        status="pass" if health_ok else "fail",
        summary=f"/api/health returned {health_code}",
        observed=health_code,
        expected=200,
        evidence=health,
        remediation="Ensure hosaka-webserver.service is running and reachable on the selected host/port.",
        source_kind="http",
    ))

    system_info_code, system_info = _http_json(host, "/api/v1/system/info", token)
    artifacts["system_info"] = system_info
    system_ok = system_info_code == 200 and isinstance(system_info, dict)
    checks.append(_check(
        slug="api.system_info",
        category="api",
        priority="p1",
        status="pass" if system_ok else "warn",
        summary=f"/api/v1/system/info returned {system_info_code}",
        observed=system_info_code,
        expected=200,
        evidence=system_info,
        remediation="If this is a remote doctor run, provide a valid bearer token; local loopback runs should succeed without one.",
        source_kind="http",
    ))

    if git_head and isinstance(health, dict) and health.get("commit"):
        commit_matches = str(health.get("commit")) == git_head
        checks.append(_check(
            slug="update.commit_alignment",
            category="update",
            priority="p2",
            status="pass" if commit_matches else "warn",
            summary="running API commit matches repo checkout" if commit_matches else "running API commit differs from repo checkout",
            observed={"api": health.get("commit"), "repo": git_head},
            remediation="Run `hosaka update` to rebuild/redeploy this checkout so the served API matches the repo HEAD.",
            source_kind="derived",
        ))

    if isinstance(health, dict):
        capability_snapshot = {
            "public_mode": health.get("public_mode"),
            "nodes_ui_enabled": health.get("nodes_ui_enabled"),
            "tailscale_api_enabled": health.get("tailscale_api_enabled"),
            "sync_enabled": health.get("sync_enabled"),
            "inbox_enabled": health.get("inbox_enabled"),
        }
        artifacts["capabilities"] = capability_snapshot
        cap_ok = not (health.get("public_mode") and any(bool(health.get(k)) for k in ("nodes_ui_enabled", "tailscale_api_enabled", "sync_enabled")))
        checks.append(_check(
            slug="api.capability_posture",
            category="api",
            priority="p1",
            status="pass" if cap_ok else "warn",
            summary="capability flags look coherent for the current public/local posture",
            observed=capability_snapshot,
            remediation="Public mode should fail closed for nodes, tailscale, and sync surfaces.",
            source_kind="http",
        ))

    tailscale_code, tailscale = _http_json(host, "/api/tailscale/status", token)
    artifacts["tailscale_status"] = tailscale
    tailscale_enabled = bool(isinstance(health, dict) and health.get("tailscale_api_enabled", True))
    if tailscale_enabled:
        t_status = "pass" if tailscale_code == 200 and isinstance(tailscale, dict) and tailscale.get("installed") else "warn"
        t_summary = f"/api/tailscale/status returned {tailscale_code}"
    else:
        t_status = "skip"
        t_summary = "tailscale API disabled by capability flags"
    checks.append(_check(
        slug="network.tailscale_status",
        category="network",
        priority="p0",
        status=t_status,
        summary=t_summary,
        observed=tailscale,
        remediation="Install/connect Tailscale or enable the local tailscale API surface if this node should participate in tailnet discovery.",
        source_kind="http",
    ))

    beacon_code, beacon = _http_json(host, "/api/beacon", token)
    artifacts["beacon"] = beacon
    beacon_present = beacon_code == 200 and isinstance(beacon, dict) and isinstance(beacon.get("self"), dict)
    checks.append(_check(
        slug="network.beacon",
        category="network",
        priority="p1",
        status="pass" if beacon_present else "warn",
        summary=f"/api/beacon returned {beacon_code}",
        observed={"protocol": beacon.get("protocol") if isinstance(beacon, dict) else None, "peer_count": len(beacon.get("peers") or []) if isinstance(beacon, dict) else None},
        remediation="Beacon metadata should be available on local builds; if missing, check the Nodes/beacon code path and capability flags.",
        source_kind="http",
    ))

    nodes_code, nodes = _http_json(host, "/api/nodes", token, timeout=10.0)
    artifacts["nodes"] = nodes
    nodes_enabled = bool(isinstance(health, dict) and health.get("nodes_ui_enabled", True))
    if nodes_enabled:
        node_list = nodes.get("nodes") if isinstance(nodes, dict) else None
        reachable = [n for n in (node_list or []) if isinstance(n, dict) and n.get("reachable")]
        connected = bool(isinstance(nodes, dict) and nodes.get("connected"))
        nodes_status = "pass"
        if nodes_code != 200:
            nodes_status = "warn"
        elif connected and isinstance(node_list, list) and len(node_list) > 0 and len(reachable) == 0:
            nodes_status = "warn"
        summary = f"/api/nodes returned {nodes_code}; peers={len(node_list) if isinstance(node_list, list) else 0}, reachable={len(reachable)}"
        remediation = None
        if nodes_status == "warn":
            remediation = "If peers are visible but unreachable, verify the remote Hosaka webserver is listening on 0.0.0.0:8421 and not only 127.0.0.1."
        checks.append(_check(
            slug="network.nodes_probe",
            category="network",
            priority="p0",
            status=nodes_status,
            summary=summary,
            observed={"connected": connected, "reachable_hosakas": len(reachable)},
            evidence={"sample": (node_list or [])[:5] if isinstance(node_list, list) else None},
            remediation=remediation,
            source_kind="http",
        ))
    else:
        checks.append(_check(
            slug="network.nodes_probe",
            category="network",
            priority="p0",
            status="skip",
            summary="nodes UI disabled by capability flags",
            source_kind="http",
        ))

    if local_profile:
        persistence_path = _persistence_path_for_profile(profile)
        persistence_ok = bool(persistence_path and persistence_path.exists() and os.access(persistence_path, os.W_OK))
        checks.append(_check(
            slug="persistence.state_dir",
            category="persistence",
            priority="p2",
            status="pass" if persistence_ok else ("warn" if persistence_path else "skip"),
            summary=(
                f"state dir {'writable' if persistence_ok else 'missing or not writable'} at {persistence_path}"
                if persistence_path
                else "no local persistence path expected for this profile"
            ),
            observed=str(persistence_path) if persistence_path else None,
            remediation="Ensure the Hosaka state directory exists and is writable so local inbox/beacon/state persistence survives restarts.",
            source_kind="host",
        ))

        checks.append(_check(
            slug="update.git_clean",
            category="update",
            priority="p3",
            status="pass" if git_clean else ("warn" if git_clean is False else "skip"),
            summary="repo working tree clean" if git_clean else ("repo has local changes" if git_clean is False else "git status unavailable"),
            observed=git_clean,
            remediation="Commit or stash local changes before trusting `hosaka update` to fast-forward cleanly.",
            source_kind="host",
        ))

    redacted_checks = _redact(checks, redact)
    redacted_artifacts = _redact(artifacts, redact)
    failed = sum(1 for c in checks if c["status"] == "fail")
    warned = sum(1 for c in checks if c["status"] == "warn")
    skipped = sum(1 for c in checks if c["status"] == "skip")
    passed = sum(1 for c in checks if c["status"] == "pass")

    next_actions = [c["remediation"] for c in checks if c.get("remediation") and c["status"] in {"fail", "warn"}]

    overall = "fail" if failed else ("warn" if warned else "pass")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "profile": profile,
        "host": host,
        "overall_status": overall,
        "summary": {
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "skipped": skipped,
            "recommended_exit_code": 1 if failed else 0,
        },
        "runtime": {
            "surface": profile,
            "boot_mode": runtime_mode,
            "repo_root": str(REPO_ROOT),
            "git_head": git_head,
        },
        "checks": redacted_checks,
        "artifacts": redacted_artifacts,
        "next_actions": next_actions[:10],
    }


def _print_human(report: dict[str, Any]) -> None:
    print(f"hosaka doctor · profile={report['profile']} · host={report['host']}")
    print(f"overall: {report['overall_status']}")
    print()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for check in report["checks"]:
        grouped.setdefault(check["category"], []).append(check)
    for category in sorted(grouped):
        print(category)
        for check in grouped[category]:
            status = check["status"].upper().ljust(5)
            print(f"  [{status}] {check['slug']}: {check['summary']}")
            remediation = check.get("remediation")
            if remediation and check["status"] in {"fail", "warn"}:
                print(f"         → {remediation}")
        print()
    summary = report["summary"]
    print(
        f"summary: {summary['passed']} passed · {summary['warned']} warned · "
        f"{summary['failed']} failed · {summary['skipped']} skipped",
    )
    if report.get("next_actions"):
        print("next actions")
        for idx, item in enumerate(report["next_actions"], start=1):
            print(f"  {idx}. {item}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hosaka runtime diagnostics")
    parser.add_argument("--profile", default="auto", choices=["auto", "appliance", "desktop", "docker-dev", "remote", "hosted-public"])
    parser.add_argument("--host", default=DEFAULT_WEB_HOST, help="Base URL to probe (default: http://127.0.0.1:8421)")
    parser.add_argument("--token", default=os.getenv("HOSAKA_API_TOKEN") or os.getenv("HOSAKA_TOKEN"), help="Bearer token for remote /api/v1 reads if needed")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings as well as failures")
    parser.add_argument("--no-redact", action="store_true", help="Do not redact sensitive-looking fields in output artifacts")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    profile = _detect_profile(args.profile, args.host)
    report = build_report(args.host, args.token, profile, redact=not args.no_redact)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    failed = report["summary"]["failed"]
    warned = report["summary"]["warned"]
    if failed:
        return 1
    if args.strict and warned:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
