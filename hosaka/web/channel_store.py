"""Single-channel message store with SHA-256 hash chaining (tamper-evident log).

Persists to JSON on disk — default ``/var/lib/hosaka/channel.json`` on the
appliance (SD card), or ``~/.hosaka/channel.json`` when unset / not writable.

Future: swap backend for Postgres / cloud sync; keep the same wire shape.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional

_TAG_RE = re.compile(r"#([a-zA-Z0-9_]{1,48})")

_MAX_MESSAGES = 8000
_MAX_TEXT = int(os.getenv("HOSAKA_CHANNEL_MAX_CHARS", "4000"))


def _default_path() -> Path:
    env = os.getenv("HOSAKA_CHANNEL_PATH", "").strip()
    if env:
        return Path(env)
    p = Path("/var/lib/hosaka/channel.json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # probe write
        if os.access(p.parent, os.W_OK):
            return p
    except OSError:
        pass
    home = Path.home()
    d = home / ".hosaka"
    d.mkdir(parents=True, exist_ok=True)
    return d / "channel.json"


CHANNEL_PATH = _default_path()
LOCK_PATH = CHANNEL_PATH.parent / ".channel.lock"


def _genesis_prev() -> str:
    return hashlib.sha256(b"hosaka-channel-genesis-v1").hexdigest()


def _extract_tags(text: str, extra: list[str]) -> list[str]:
    found = {m.group(1).lower() for m in _TAG_RE.finditer(text)}
    for t in extra:
        t = t.strip().lstrip("#").lower()
        if t and len(t) <= 48:
            found.add(t)
    return sorted(found)


def _canonical_record(
    prev_hash: str,
    mid: str,
    at: int,
    author: str,
    text: str,
    tags: list[str],
    parent_id: Optional[str],
) -> str:
    payload = {
        "at": at,
        "author": author,
        "id": mid,
        "parent_id": parent_id,
        "prev_hash": prev_hash,
        "tags": tags,
        "text": text,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{prev_hash}|{blob}".encode()).hexdigest()


def _load_raw() -> dict[str, Any]:
    if not CHANNEL_PATH.exists():
        return {"version": 1, "chain_head": _genesis_prev(), "messages": []}
    try:
        return json.loads(CHANNEL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "chain_head": _genesis_prev(), "messages": []}


def _save_raw(data: dict[str, Any]) -> None:
    CHANNEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHANNEL_PATH.with_suffix(".json.tmp")
    text = json.dumps(data, indent=2, ensure_ascii=False)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(CHANNEL_PATH)


def _with_lock(mutate: Any) -> Any:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            return mutate()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def list_messages() -> tuple[list[dict[str, Any]], str]:
    """Return (messages, chain_head_hex)."""

    def _read() -> tuple[list[dict[str, Any]], str]:
        data = _load_raw()
        msgs = data.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []
        head = str(data.get("chain_head") or _genesis_prev())
        return msgs, head

    return _with_lock(_read)


def append_message(
    text: str,
    author: str = "operator",
    parent_id: Optional[str] = None,
    extra_tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    text = (text or "").strip()
    if not text or len(text) > _MAX_TEXT:
        raise ValueError("empty or too long")
    author = (author or "operator").strip()[:64] or "operator"
    extra_tags = extra_tags or []
    tags = _extract_tags(text, extra_tags)

    def _append() -> dict[str, Any]:
        data = _load_raw()
        msgs: list[dict[str, Any]] = data.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []
        head = str(data.get("chain_head") or _genesis_prev())
        mid = uuid.uuid4().hex
        at = int(__import__("time").time() * 1000)

        if parent_id:
            if not any(m.get("id") == parent_id for m in msgs):
                raise ValueError("parent not found")

        msg_hash = _canonical_record(head, mid, at, author, text, tags, parent_id)
        row = {
            "at": at,
            "author": author,
            "hash": msg_hash,
            "id": mid,
            "parent_id": parent_id,
            "prev_hash": head,
            "tags": tags,
            "text": text,
        }
        msgs.append(row)
        if len(msgs) > _MAX_MESSAGES:
            msgs = msgs[-_MAX_MESSAGES:]
        data["messages"] = msgs
        data["chain_head"] = msg_hash
        data["version"] = 1
        _save_raw(data)
        return row

    return _with_lock(_append)


def verify_chain() -> bool:
    """Return True if stored hashes match recomputed chain."""
    data = _load_raw()
    msgs: list[dict[str, Any]] = data.get("messages") or []
    if not msgs:
        return True
    head = _genesis_prev()
    for m in msgs:
        if not isinstance(m, dict):
            return False
        mid = m.get("id")
        at = m.get("at")
        author = m.get("author", "")
        text = m.get("text", "")
        tags = m.get("tags") or []
        parent_id = m.get("parent_id")
        prev = m.get("prev_hash")
        if prev != head:
            return False
        expect = _canonical_record(
            str(prev),
            str(mid),
            int(at),
            str(author),
            str(text),
            list(tags) if isinstance(tags, list) else [],
            str(parent_id) if parent_id else None,
        )
        if m.get("hash") != expect:
            return False
        head = expect
    return str(data.get("chain_head")) == head
