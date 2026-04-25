"""Append-only inbox / notifications store.

This is Hosaka's first generic event log for operator-facing notices.
It is intentionally conservative:

- append-only on disk
- hash-chained for tamper evidence
- deduped by stable event id
- supports two event kinds today: `notify` and `ack`

The inbox is *not* a binary sync channel. Only small metadata/event payloads
belong here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

_TAG_RE = re.compile(r"#([a-zA-Z0-9_]{1,48})")
_SEVERITIES = {"info", "success", "warn", "error"}
_KINDS = {"notify", "ack"}
_MAX_EVENTS = int(os.getenv("HOSAKA_INBOX_MAX_EVENTS", "12000"))
_MAX_TITLE = int(os.getenv("HOSAKA_INBOX_MAX_TITLE", "140"))
_MAX_BODY = int(os.getenv("HOSAKA_INBOX_MAX_BODY", "4000"))


def _default_path() -> Path:
    env = os.getenv("HOSAKA_INBOX_PATH", "").strip()
    if env:
        return Path(env)
    p = Path("/var/lib/hosaka/inbox.json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if os.access(p.parent, os.W_OK):
            return p
    except OSError:
        pass
    home = Path.home()
    d = home / ".hosaka"
    d.mkdir(parents=True, exist_ok=True)
    return d / "inbox.json"


INBOX_PATH = _default_path()
LOCK_PATH = INBOX_PATH.parent / ".inbox.lock"


def _genesis_prev() -> str:
    return hashlib.sha256(b"hosaka-inbox-genesis-v1").hexdigest()


def _extract_tags(title: str, body: str, extra: list[str]) -> list[str]:
    found = {m.group(1).lower() for m in _TAG_RE.finditer(f"{title}\n{body}")}
    for t in extra:
        t = t.strip().lstrip("#").lower()
        if t and len(t) <= 48:
            found.add(t)
    return sorted(found)


def _canonical_record(
    prev_hash: str,
    eid: str,
    at: int,
    kind: str,
    author: str,
    node_id: str,
    topic: str,
    severity: str,
    title: str,
    body: str,
    tags: list[str],
    target: str,
    event_ref: str | None,
) -> str:
    payload = {
        "at": at,
        "author": author,
        "body": body,
        "event_ref": event_ref,
        "id": eid,
        "kind": kind,
        "node_id": node_id,
        "prev_hash": prev_hash,
        "severity": severity,
        "tags": tags,
        "target": target,
        "title": title,
        "topic": topic,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{prev_hash}|{blob}".encode()).hexdigest()


def _load_raw() -> dict[str, Any]:
    if not INBOX_PATH.exists():
        return {"version": 1, "chain_head": _genesis_prev(), "events": []}
    try:
        return json.loads(INBOX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "chain_head": _genesis_prev(), "events": []}


def _save_raw(data: dict[str, Any]) -> None:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = INBOX_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INBOX_PATH)


def _with_lock(mutate: Any) -> Any:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            return mutate()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _sanitize_event(
    *,
    kind: str,
    author: str,
    node_id: str,
    topic: str,
    severity: str,
    title: str,
    body: str,
    target: str,
    tags: list[str],
    event_ref: str | None,
    eid: str | None = None,
    at: int | None = None,
) -> dict[str, Any]:
    kind = (kind or "notify").strip().lower()
    if kind not in _KINDS:
        raise ValueError("invalid kind")
    author = (author or "operator").strip()[:64] or "operator"
    node_id = (node_id or "unknown").strip()[:128] or "unknown"
    topic = (topic or "general").strip().lower()[:64] or "general"
    severity = (severity or "info").strip().lower()
    if severity not in _SEVERITIES:
        severity = "info"
    title = (title or "").strip()[:_MAX_TITLE]
    body = (body or "").strip()[:_MAX_BODY]
    target = (target or "broadcast").strip()[:128] or "broadcast"
    event_ref = (event_ref or "").strip()[:64] or None

    if kind == "notify" and not (title or body):
        raise ValueError("empty notification")
    if kind == "ack" and not event_ref:
        raise ValueError("ack requires event_ref")

    safe_tags = _extract_tags(title, body, tags)
    when = int(at) if at is not None else int(time.time() * 1000)
    event_id = (eid or uuid.uuid4().hex).strip()[:64]
    return {
        "id": event_id,
        "at": when,
        "kind": kind,
        "author": author,
        "node_id": node_id,
        "topic": topic,
        "severity": severity,
        "title": title,
        "body": body,
        "target": target,
        "tags": safe_tags,
        "event_ref": event_ref,
    }


def list_events(limit: int | None = None) -> tuple[list[dict[str, Any]], str]:
    def _read() -> tuple[list[dict[str, Any]], str]:
        data = _load_raw()
        events = data.get("events") or []
        if not isinstance(events, list):
            events = []
        if limit is not None and limit > 0:
            events = events[-limit:]
        head = str(data.get("chain_head") or _genesis_prev())
        return events, head

    return _with_lock(_read)


def append_notification(
    title: str,
    body: str = "",
    *,
    author: str = "operator",
    node_id: str = "unknown",
    topic: str = "general",
    severity: str = "info",
    target: str = "broadcast",
    tags: list[str] | None = None,
    eid: str | None = None,
    at: int | None = None,
) -> dict[str, Any]:
    payload = _sanitize_event(
        kind="notify",
        author=author,
        node_id=node_id,
        topic=topic,
        severity=severity,
        title=title,
        body=body,
        target=target,
        tags=tags or [],
        event_ref=None,
        eid=eid,
        at=at,
    )
    return _append(payload)


def append_ack(
    event_ref: str,
    *,
    author: str = "operator",
    node_id: str = "unknown",
    topic: str = "general",
    target: str = "broadcast",
    eid: str | None = None,
    at: int | None = None,
) -> dict[str, Any]:
    payload = _sanitize_event(
        kind="ack",
        author=author,
        node_id=node_id,
        topic=topic,
        severity="success",
        title="",
        body="",
        target=target,
        tags=[],
        event_ref=event_ref,
        eid=eid,
        at=at,
    )
    return _append(payload)


def _append(payload: dict[str, Any]) -> dict[str, Any]:
    def _mutate() -> dict[str, Any]:
        data = _load_raw()
        events = data.get("events") or []
        if not isinstance(events, list):
            events = []
        for row in events:
            if isinstance(row, dict) and row.get("id") == payload["id"]:
                return row
        if payload["kind"] == "ack":
            ref = payload.get("event_ref")
            if not any(isinstance(row, dict) and row.get("id") == ref for row in events):
                raise ValueError("event_ref not found")
        head = str(data.get("chain_head") or _genesis_prev())
        row = dict(payload)
        row["prev_hash"] = head
        row["hash"] = _canonical_record(
            head,
            str(row["id"]),
            int(row["at"]),
            str(row["kind"]),
            str(row["author"]),
            str(row["node_id"]),
            str(row["topic"]),
            str(row["severity"]),
            str(row["title"]),
            str(row["body"]),
            list(row.get("tags") or []),
            str(row.get("target") or "broadcast"),
            str(row["event_ref"]) if row.get("event_ref") else None,
        )
        events.append(row)
        if len(events) > _MAX_EVENTS:
            events = events[-_MAX_EVENTS:]
        data["events"] = events
        data["chain_head"] = row["hash"]
        data["version"] = 1
        _save_raw(data)
        return row

    return _with_lock(_mutate)


def ingest_event(raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    kind = str(raw.get("kind") or "notify")
    payload = _sanitize_event(
        kind=kind,
        author=str(raw.get("author") or "operator"),
        node_id=str(raw.get("node_id") or "unknown"),
        topic=str(raw.get("topic") or "general"),
        severity=str(raw.get("severity") or "info"),
        title=str(raw.get("title") or ""),
        body=str(raw.get("body") or ""),
        target=str(raw.get("target") or "broadcast"),
        tags=list(raw.get("tags") or []),
        event_ref=str(raw.get("event_ref")) if raw.get("event_ref") else None,
        eid=str(raw.get("id") or uuid.uuid4().hex),
        at=int(raw.get("at") or int(time.time() * 1000)),
    )

    def _mutate() -> tuple[dict[str, Any], bool]:
        data = _load_raw()
        events = data.get("events") or []
        if not isinstance(events, list):
            events = []
        for row in events:
            if isinstance(row, dict) and row.get("id") == payload["id"]:
                return row, False
        head = str(data.get("chain_head") or _genesis_prev())
        row = dict(payload)
        row["prev_hash"] = head
        row["hash"] = _canonical_record(
            head,
            str(row["id"]),
            int(row["at"]),
            str(row["kind"]),
            str(row["author"]),
            str(row["node_id"]),
            str(row["topic"]),
            str(row["severity"]),
            str(row["title"]),
            str(row["body"]),
            list(row.get("tags") or []),
            str(row.get("target") or "broadcast"),
            str(row["event_ref"]) if row.get("event_ref") else None,
        )
        events.append(row)
        if len(events) > _MAX_EVENTS:
            events = events[-_MAX_EVENTS:]
        data["events"] = events
        data["chain_head"] = row["hash"]
        data["version"] = 1
        _save_raw(data)
        return row, True

    return _with_lock(_mutate)


def list_notifications(limit: int = 200) -> tuple[list[dict[str, Any]], str, bool]:
    events, head = list_events()
    notifications: dict[str, dict[str, Any]] = {}
    acked: dict[str, dict[str, Any]] = {}

    for row in events:
        if not isinstance(row, dict):
            continue
        kind = row.get("kind")
        if kind == "notify":
            notifications[str(row.get("id"))] = dict(row)
        elif kind == "ack" and row.get("event_ref"):
            acked[str(row.get("event_ref"))] = dict(row)

    out: list[dict[str, Any]] = []
    for event_id, note in notifications.items():
        item = dict(note)
        ack = acked.get(event_id)
        item["acked"] = ack is not None
        item["ack_at"] = ack.get("at") if ack else None
        item["ack_author"] = ack.get("author") if ack else None
        out.append(item)

    out.sort(key=lambda row: int(row.get("at") or 0), reverse=True)
    if limit > 0:
        out = out[:limit]
    return out, head, verify_chain()


def verify_chain() -> bool:
    data = _load_raw()
    events = data.get("events") or []
    if not events:
        return True
    head = _genesis_prev()
    for row in events:
        if not isinstance(row, dict):
            return False
        prev = str(row.get("prev_hash") or "")
        if prev != head:
            return False
        expect = _canonical_record(
            prev,
            str(row.get("id") or ""),
            int(row.get("at") or 0),
            str(row.get("kind") or "notify"),
            str(row.get("author") or "operator"),
            str(row.get("node_id") or "unknown"),
            str(row.get("topic") or "general"),
            str(row.get("severity") or "info"),
            str(row.get("title") or ""),
            str(row.get("body") or ""),
            list(row.get("tags") or []),
            str(row.get("target") or "broadcast"),
            str(row.get("event_ref")) if row.get("event_ref") else None,
        )
        if str(row.get("hash") or "") != expect:
            return False
        head = expect
    return str(data.get("chain_head") or "") == head