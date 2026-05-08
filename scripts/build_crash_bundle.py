#!/usr/bin/env python3
"""build_crash_bundle.py — phase 11.

Produce a bounded, redacted tarball capturing what was happening on this box
right before something went wrong. Stdlib only. Never raises (best-effort).

The bundle contains:
  manifest.json         summary, redaction list, byte sizes
  events.jsonl          last 30 min from runtime/observability/events.db
  obs_stats.json        sink counters at bundle time
  features.yaml         snapshot of docs/hosaka.features.yaml
  agent_context.json    snapshot of docs/agent_context.json (if present)
  context.json          host info: hostname, uptime, git ref, py version
  stack.txt             optional --stack <file>
  notes.txt             optional --reason "..." text

Hard caps:
  * total bundle <= HOSAKA_CRASH_MAX_BYTES (default 5 MiB).
  * events trimmed oldest-first if needed.

Usage:
    python scripts/build_crash_bundle.py
    python scripts/build_crash_bundle.py --reason "kiosk froze" --stack /tmp/trace.txt
    python scripts/build_crash_bundle.py --window-min 60 --out /tmp/bundle.tgz
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import socket
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "runtime" / "observability" / "events.db"
DEFAULT_OUT_DIR = REPO_ROOT / "runtime" / "crashes"
MAX_BYTES = int(os.getenv("HOSAKA_CRASH_MAX_BYTES", str(5 * 1024 * 1024)))

# Patterns that, if they show up in payload_json, get scrubbed.
DEFAULT_REDACT_PATTERNS = [
    r"(?i)(api[_-]?key|secret|token|password|passphrase)\s*[:=]\s*\"?[A-Za-z0-9._\-]{8,}\"?",
    r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}",
    r"sk-[A-Za-z0-9]{20,}",
]


def _redactors() -> list[re.Pattern]:
    extra = os.getenv("HOSAKA_OBS_REDACT", "")
    pats = list(DEFAULT_REDACT_PATTERNS)
    if extra:
        pats.extend([p.strip() for p in extra.split("|") if p.strip()])
    return [re.compile(p) for p in pats]


def _redact(text: str, regexes: list[re.Pattern]) -> str:
    out = text
    for r in regexes:
        out = r.sub("[REDACTED]", out)
    return out


def _safe_run(cmd: list[str], timeout: int = 3) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return (p.stdout or p.stderr or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _read_events(db: Path, window_min: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info = {"db_exists": db.exists(), "rows_in_window": 0, "rows_total": 0}
    if not db.exists():
        return [], info
    try:
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        info["db_error"] = str(exc)
        return [], info
    try:
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - window_min * 60))
        rows = con.execute(
            "SELECT * FROM events WHERE ts_utc >= ? ORDER BY id ASC", (cutoff,)
        ).fetchall()
        (total,) = con.execute("SELECT COUNT(*) FROM events").fetchone()
        info["rows_total"] = int(total)
        info["rows_in_window"] = len(rows)
        return [dict(r) for r in rows], info
    except sqlite3.Error as exc:
        info["db_error"] = str(exc)
        return [], info
    finally:
        try:
            con.close()
        except Exception:
            pass


def _events_to_jsonl(events: list[dict[str, Any]], regexes: list[re.Pattern]) -> bytes:
    buf = io.BytesIO()
    for ev in events:
        line = json.dumps(ev, default=str, separators=(",", ":"))
        line = _redact(line, regexes)
        buf.write(line.encode("utf-8"))
        buf.write(b"\n")
    return buf.getvalue()


def _trim_to_cap(events_jsonl: bytes, hard_cap: int) -> tuple[bytes, int]:
    if len(events_jsonl) <= hard_cap:
        return events_jsonl, 0
    # drop oldest lines until under cap
    lines = events_jsonl.splitlines(keepends=True)
    dropped = 0
    while lines and sum(len(l) for l in lines) > hard_cap:
        lines.pop(0)
        dropped += 1
    return b"".join(lines), dropped


def _host_context() -> dict[str, Any]:
    git_ref = _safe_run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"])
    git_branch = _safe_run(["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"])
    uptime = ""
    try:
        with open("/proc/uptime", "r") as fh:
            uptime = fh.read().split()[0]
    except OSError:
        pass
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "git_commit": git_ref,
        "git_branch": git_branch,
        "uptime_seconds": uptime,
    }


def _obs_stats() -> dict[str, Any]:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from hosaka import obs as _obs  # type: ignore

        return _obs.get_stats()
    except Exception as exc:
        return {"error": f"obs not importable: {exc}"}


def build_bundle(
    *,
    db_path: Path,
    out_path: Path,
    window_min: int,
    reason: str,
    stack_file: Path | None,
    max_bytes: int,
) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    regexes = _redactors()

    events, ev_info = _read_events(db_path, window_min)
    events_jsonl = _events_to_jsonl(events, regexes)
    # Reserve ~256 KiB for everything else; trim events to fit.
    cap_for_events = max(64 * 1024, max_bytes - 256 * 1024)
    events_jsonl, dropped = _trim_to_cap(events_jsonl, cap_for_events)

    catalog_path = REPO_ROOT / "docs" / "hosaka.features.yaml"
    agent_ctx_path = REPO_ROOT / "docs" / "agent_context.json"

    bundle_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    manifest = {
        "schema_version": "1",
        "bundle_id": bundle_id,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": reason,
        "window_minutes": window_min,
        "max_bytes": max_bytes,
        "events": {
            **ev_info,
            "rows_after_trim": events_jsonl.count(b"\n") if events_jsonl else 0,
            "dropped_for_cap": dropped,
        },
        "redaction_pattern_count": len(regexes),
        "stack_included": bool(stack_file and stack_file.exists()),
    }

    with tarfile.open(out_path, "w:gz") as tf:
        def _add_bytes(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = int(time.time())
            tf.addfile(info, io.BytesIO(data))

        _add_bytes("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))
        _add_bytes("events.jsonl", events_jsonl)
        _add_bytes("obs_stats.json", json.dumps(_obs_stats(), indent=2).encode("utf-8"))
        _add_bytes("context.json", json.dumps(_host_context(), indent=2).encode("utf-8"))
        if catalog_path.exists():
            _add_bytes("features.yaml", catalog_path.read_bytes())
        if agent_ctx_path.exists():
            _add_bytes("agent_context.json", agent_ctx_path.read_bytes())
        if stack_file and stack_file.exists():
            try:
                _add_bytes("stack.txt", _redact(stack_file.read_text(errors="replace"), regexes).encode("utf-8"))
            except OSError:
                pass
        if reason:
            _add_bytes("notes.txt", reason.encode("utf-8"))

    manifest["bundle_path"] = str(out_path)
    manifest["bundle_bytes"] = out_path.stat().st_size
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=None, help="output .tgz path")
    ap.add_argument("--window-min", type=int, default=30)
    ap.add_argument("--reason", default="manual")
    ap.add_argument("--stack", default=None, help="optional file with a stack trace")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    args = ap.parse_args()

    out = Path(args.out) if args.out else (
        DEFAULT_OUT_DIR / f"crash-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.tgz"
    )
    try:
        manifest = build_bundle(
            db_path=Path(args.db),
            out_path=out,
            window_min=args.window_min,
            reason=args.reason,
            stack_file=Path(args.stack) if args.stack else None,
            max_bytes=args.max_bytes,
        )
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
