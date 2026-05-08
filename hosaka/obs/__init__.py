"""hosaka.obs — proof-of-life telemetry that cannot crash hosaka.

Public surface (this is the WHOLE api):

    from hosaka.obs import emit, trace, heartbeat, get_stats

    emit("CUSTOM_EVENT", feature_id="foo", level="info", **fields)

    @trace("feature.foo")
    def my_handler(...): ...

    @heartbeat("hosaka.web", interval_s=300)
    def __module_loaded__(): ...   # or just: heartbeat("hosaka.web")() at import time

Hard guarantees (see docs/increased_observability.yaml phase 07/08):

* Importing this module never opens a network connection.
* `emit` and the decorators NEVER raise. Failures bump counters.
* The sink writer thread is supervised: on crash it restarts with backoff.
  If it dies permanently the queue drains to /dev/null and decorators no-op.
* Disabled mode (HOSAKA_OBS=off) makes everything a no-op with < 1µs overhead.
* Stdlib only. No ORM, no migrations, no third-party deps.

Storage: sqlite WAL at $HOSAKA_OBS_DB (default runtime/observability/events.db).
Retention: 24h rolling, opportunistic eviction every Nth insert + hard row cap.
"""
from __future__ import annotations

import functools
import os
import queue
import random
import sqlite3
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

# ── config (env-driven, all optional) ────────────────────────────────────────

_ENABLED = os.getenv("HOSAKA_OBS", "on").lower() not in ("0", "off", "false", "no")
_DB_PATH = Path(
    os.getenv(
        "HOSAKA_OBS_DB",
        str(Path(__file__).resolve().parents[2] / "runtime" / "observability" / "events.db"),
    )
)
_QUEUE_MAX = int(os.getenv("HOSAKA_OBS_QUEUE_MAX", "4096"))
_BATCH_SIZE = int(os.getenv("HOSAKA_OBS_BATCH_SIZE", "200"))
_BATCH_INTERVAL_MS = int(os.getenv("HOSAKA_OBS_BATCH_INTERVAL_MS", "250"))
_MAX_PAYLOAD = int(os.getenv("HOSAKA_OBS_MAX_PAYLOAD", "4096"))
_RETENTION_HOURS = float(os.getenv("HOSAKA_OBS_RETENTION_HOURS", "24"))
_ROW_CAP = int(os.getenv("HOSAKA_OBS_ROW_CAP", "250000"))
_EVICT_EVERY = int(os.getenv("HOSAKA_OBS_EVICT_EVERY", "1000"))

_SESSION_ID = os.getenv("HOSAKA_SESSION_ID") or uuid.uuid4().hex[:12]

# ── counters (sole source of obs-internal health) ────────────────────────────

_stats_lock = threading.Lock()
_stats: dict[str, int] = {
    "emitted": 0,
    "dropped_queue_full": 0,
    "dropped_disabled": 0,
    "written": 0,
    "write_errors": 0,
    "sink_restarts": 0,
    "decorator_errors": 0,
}


def _bump(key: str, n: int = 1) -> None:
    # Best-effort, never raises. Counter contention is harmless.
    try:
        with _stats_lock:
            _stats[key] = _stats.get(key, 0) + n
    except Exception:
        pass


def get_stats() -> dict[str, int]:
    """Snapshot of internal counters. Safe to call anywhere."""
    try:
        with _stats_lock:
            return dict(_stats)
    except Exception:
        return {}


# ── queue + writer thread ────────────────────────────────────────────────────

_queue: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=_QUEUE_MAX)
_writer_thread: Optional[threading.Thread] = None
_writer_lock = threading.Lock()
_shutdown = threading.Event()
_insert_count = 0  # only touched by writer thread


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc          TEXT    NOT NULL,
            ts_mono         REAL    NOT NULL,
            session_id      TEXT    NOT NULL,
            correlation_id  TEXT,
            kind            TEXT    NOT NULL,
            feature_id      TEXT,
            source          TEXT    NOT NULL,
            level           TEXT    NOT NULL,
            status          TEXT,
            duration_ms     REAL,
            payload_json    TEXT
        )
        """
    )
    # Additive-only indexes. Never drop.
    for ddl in (
        "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_utc)",
        "CREATE INDEX IF NOT EXISTS idx_events_kind_ts ON events(kind, ts_utc)",
        "CREATE INDEX IF NOT EXISTS idx_events_feature_ts ON events(feature_id, ts_utc)",
        "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)",
    ):
        con.execute(ddl)
    con.commit()


def _open_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), isolation_level=None, check_same_thread=False)
    _ensure_schema(con)
    return con


def _evict(con: sqlite3.Connection) -> None:
    cutoff_epoch = time.time() - (_RETENTION_HOURS * 3600.0)
    cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff_epoch))
    try:
        con.execute("DELETE FROM events WHERE ts_utc < ?", (cutoff_iso,))
        # Hard row cap: oldest-first FIFO.
        cur = con.execute("SELECT COUNT(*) FROM events")
        (n,) = cur.fetchone()
        if n > _ROW_CAP:
            over = n - _ROW_CAP
            con.execute(
                "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id ASC LIMIT ?)",
                (over,),
            )
    except sqlite3.Error:
        _bump("write_errors")


def _flush(con: sqlite3.Connection, batch: list[dict[str, Any]]) -> None:
    global _insert_count
    if not batch:
        return
    rows = [
        (
            ev["ts_utc"],
            ev["ts_mono"],
            ev["session_id"],
            ev.get("correlation_id"),
            ev["kind"],
            ev.get("feature_id"),
            ev["source"],
            ev["level"],
            ev.get("status"),
            ev.get("duration_ms"),
            ev.get("payload_json"),
        )
        for ev in batch
    ]
    try:
        con.executemany(
            """INSERT INTO events
               (ts_utc, ts_mono, session_id, correlation_id, kind, feature_id,
                source, level, status, duration_ms, payload_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        _bump("written", len(rows))
        _insert_count += len(rows)
        if _insert_count >= _EVICT_EVERY:
            _evict(con)
            _insert_count = 0
    except sqlite3.Error:
        _bump("write_errors")


def _writer_loop() -> None:
    backoff = 0.5
    while not _shutdown.is_set():
        try:
            con = _open_db()
            backoff = 0.5  # reset after a healthy open
            batch: list[dict[str, Any]] = []
            deadline = time.monotonic() + (_BATCH_INTERVAL_MS / 1000.0)
            while not _shutdown.is_set():
                timeout = max(0.0, deadline - time.monotonic())
                try:
                    ev = _queue.get(timeout=timeout if timeout > 0 else 0.001)
                    batch.append(ev)
                except queue.Empty:
                    pass
                if len(batch) >= _BATCH_SIZE or time.monotonic() >= deadline:
                    _flush(con, batch)
                    batch = []
                    deadline = time.monotonic() + (_BATCH_INTERVAL_MS / 1000.0)
            # graceful shutdown: drain
            try:
                while True:
                    batch.append(_queue.get_nowait())
            except queue.Empty:
                pass
            _flush(con, batch)
            try:
                con.close()
            except Exception:
                pass
            return
        except Exception:
            _bump("sink_restarts")
            # never let this thread die for good; sleep + retry
            time.sleep(min(backoff, 30.0))
            backoff = min(backoff * 2.0, 30.0)


def _ensure_writer() -> None:
    global _writer_thread
    if not _ENABLED:
        return
    if _writer_thread is not None and _writer_thread.is_alive():
        return
    with _writer_lock:
        if _writer_thread is not None and _writer_thread.is_alive():
            return
        t = threading.Thread(target=_writer_loop, name="hosaka-obs-writer", daemon=True)
        t.start()
        _writer_thread = t


# ── public emit ──────────────────────────────────────────────────────────────

_LEVELS = ("debug", "info", "warn", "error", "fatal")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _truncate_payload(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        import json

        s = json.dumps(obj, default=str, separators=(",", ":"))
    except Exception:
        try:
            s = str(obj)
        except Exception:
            return None
    if len(s) > _MAX_PAYLOAD:
        s = s[: _MAX_PAYLOAD - 3] + "..."
    return s


def emit(
    event: str,
    *,
    kind: str = "custom",
    feature_id: Optional[str] = None,
    source: str = "unknown",
    level: str = "info",
    status: Optional[str] = None,
    duration_ms: Optional[float] = None,
    correlation_id: Optional[str] = None,
    payload: Any = None,
    **extra: Any,
) -> bool:
    """Fire-and-forget event emit. Returns True if queued, False otherwise.
    NEVER raises.
    """
    if not _ENABLED:
        _bump("dropped_disabled")
        return False
    try:
        if level not in _LEVELS:
            level = "info"
        merged: dict[str, Any] = {"event": event}
        if extra:
            merged.update(extra)
        if payload is not None:
            merged["payload"] = payload
        ev = {
            "ts_utc": _now_iso(),
            "ts_mono": time.monotonic(),
            "session_id": _SESSION_ID,
            "correlation_id": correlation_id,
            "kind": kind,
            "feature_id": feature_id,
            "source": source,
            "level": level,
            "status": status,
            "duration_ms": duration_ms,
            "payload_json": _truncate_payload(merged),
        }
        try:
            _queue.put_nowait(ev)
            _bump("emitted")
        except queue.Full:
            _bump("dropped_queue_full")
            return False
        _ensure_writer()
        return True
    except Exception:
        _bump("decorator_errors")
        return False


# ── decorators ───────────────────────────────────────────────────────────────


def trace(
    feature_id: str,
    *,
    sample_rate: float = 1.0,
    level: str = "info",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a function so its entry/exit/failure become events.

    sample_rate: 0.0 = never emit (overhead is one float compare), 1.0 = always.
    Exceptions inside the wrapped function are re-raised AFTER a fail event.
    Exceptions inside the wrapper itself are swallowed; call result is returned.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not _ENABLED:
            return fn
        source = f"{getattr(fn, '__module__', '?')}:{getattr(fn, '__qualname__', fn.__name__)}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sampled = sample_rate >= 1.0 or (sample_rate > 0.0 and random.random() < sample_rate)
            t0 = time.monotonic() if sampled else 0.0
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                if sampled:
                    try:
                        emit(
                            "FUNCTION_FAILED",
                            kind="function",
                            feature_id=feature_id,
                            source=source,
                            level="error",
                            status="failed",
                            duration_ms=(time.monotonic() - t0) * 1000.0,
                            payload={
                                "exc_type": type(exc).__name__,
                                "exc_msg": str(exc)[:512],
                                "stack": "".join(
                                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                                )[-2048:],
                            },
                        )
                    except Exception:
                        _bump("decorator_errors")
                raise
            if sampled:
                try:
                    emit(
                        "FUNCTION_EXITED",
                        kind="function",
                        feature_id=feature_id,
                        source=source,
                        level=level,
                        status="ok",
                        duration_ms=(time.monotonic() - t0) * 1000.0,
                    )
                except Exception:
                    _bump("decorator_errors")
            return result

        wrapper.__hosaka_traced__ = True  # type: ignore[attr-defined]
        return wrapper

    return decorator


_heartbeat_lock = threading.Lock()
_heartbeat_last: dict[str, float] = {}


def heartbeat(module_id: str, *, interval_s: float = 300.0) -> Callable[[], None]:
    """Mark a module as alive at import time and rate-limit MODULE_ALIVE events.

    Usage:

        from hosaka.obs import heartbeat
        heartbeat("hosaka.web")()      # call at import time

    Returns a callable so it can be invoked again (e.g. from a long-running loop)
    and will only emit if `interval_s` has elapsed since last beat for this id.
    """

    def beat() -> None:
        if not _ENABLED:
            return
        try:
            now = time.monotonic()
            should_emit = False
            with _heartbeat_lock:
                last = _heartbeat_last.get(module_id)
                if last is None:
                    _heartbeat_last[module_id] = now
                    should_emit = True
                    event = "MODULE_LOADED"
                elif now - last >= interval_s:
                    _heartbeat_last[module_id] = now
                    should_emit = True
                    event = "MODULE_ALIVE"
                else:
                    return
            emit(
                event,
                kind="module",
                feature_id=module_id,
                source=module_id,
                level="info",
                status="ok",
            )
        except Exception:
            _bump("decorator_errors")

    return beat


# ── shutdown hook (best-effort) ──────────────────────────────────────────────


def _shutdown_writer(timeout: float = 2.0) -> None:
    _shutdown.set()
    t = _writer_thread
    if t is not None and t.is_alive():
        try:
            t.join(timeout=timeout)
        except Exception:
            pass


import atexit as _atexit

_atexit.register(_shutdown_writer)


__all__ = [
    "emit",
    "trace",
    "heartbeat",
    "get_stats",
]
