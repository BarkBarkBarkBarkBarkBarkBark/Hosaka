"""Read-only events API (phase 08).

Exposes the local hosaka.obs event store under /api/v1/events for:

* tailing recent activity                     GET /api/v1/events
* per-feature health summary                  GET /api/v1/events/summary
* registered features that emit nothing       GET /api/v1/events/silent
* internal sink counters                      GET /api/v1/events/stats

Auth: same as api_v1 (loopback always allowed; LAN requires bearer if a token
is configured). All endpoints are read-only and bounded.

Design rules:

* Stdlib-only sqlite3, no ORM.
* Never opens the DB if obs hasn't created it yet — returns empty results.
* All queries cap LIMIT at 5000 rows hard.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from hosaka import obs as _obs
from hosaka.obs import trace, heartbeat
from hosaka.web.api_v1 import require_auth

router = APIRouter(prefix="/api/v1/events", tags=["events"])

heartbeat("hosaka.web.events_api")()

_DB_PATH = Path(
    os.getenv(
        "HOSAKA_OBS_DB",
        str(Path(__file__).resolve().parents[2] / "runtime" / "observability" / "events.db"),
    )
)
_HARD_LIMIT = 5000


def _connect() -> Optional[sqlite3.Connection]:
    if not _DB_PATH.exists():
        return None
    try:
        con = sqlite3.connect(str(_DB_PATH))
        con.row_factory = sqlite3.Row
        return con
    except sqlite3.Error:
        return None


# ── models ───────────────────────────────────────────────────────────────────


class EventOut(BaseModel):
    id: int
    ts_utc: str
    session_id: str
    correlation_id: Optional[str] = None
    kind: str
    feature_id: Optional[str] = None
    source: str
    level: str
    status: Optional[str] = None
    duration_ms: Optional[float] = None
    payload: Any = None


class EventsListOut(BaseModel):
    count: int
    events: list[EventOut]


class FeatureSummary(BaseModel):
    feature_id: str
    last_seen_utc: str
    events_total: int
    errors_1h: int
    p95_duration_ms: Optional[float] = None


class SummaryOut(BaseModel):
    window_hours: float
    features: list[FeatureSummary]


class SilentOut(BaseModel):
    silent_for_minutes: int
    features: list[str]


class StatsOut(BaseModel):
    db_exists: bool
    db_path: str
    counters: dict[str, int]


# ── helpers ──────────────────────────────────────────────────────────────────


def _row_to_event(row: sqlite3.Row) -> EventOut:
    payload: Any = None
    raw = row["payload_json"]
    if raw:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = raw
    return EventOut(
        id=int(row["id"]),
        ts_utc=row["ts_utc"],
        session_id=row["session_id"],
        correlation_id=row["correlation_id"],
        kind=row["kind"],
        feature_id=row["feature_id"],
        source=row["source"],
        level=row["level"],
        status=row["status"],
        duration_ms=row["duration_ms"],
        payload=payload,
    )


# ── endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=EventsListOut, dependencies=[Depends(require_auth)])
@trace("obs.events", sample_rate=0.1)
def list_events(
    since: Optional[str] = Query(None, description="ISO8601 UTC; only events newer than this"),
    kind: Optional[str] = Query(None, description="function|module|command|keystroke|ui|crash|health|recovery|custom"),
    feature_id: Optional[str] = None,
    level: Optional[str] = Query(None, description="debug|info|warn|error|fatal"),
    limit: int = Query(200, ge=1, le=_HARD_LIMIT),
) -> EventsListOut:
    con = _connect()
    if con is None:
        return EventsListOut(count=0, events=[])
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if since:
            clauses.append("ts_utc > ?")
            params.append(since)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if feature_id:
            clauses.append("feature_id = ?")
            params.append(feature_id)
        if level:
            clauses.append("level = ?")
            params.append(level)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM events{where} ORDER BY id DESC LIMIT ?"
        params.append(limit)
        try:
            rows = con.execute(sql, params).fetchall()
        except sqlite3.Error:
            return EventsListOut(count=0, events=[])
        events = [_row_to_event(r) for r in rows]
        return EventsListOut(count=len(events), events=events)
    finally:
        con.close()


@router.get("/summary", response_model=SummaryOut, dependencies=[Depends(require_auth)])
@trace("obs.events", sample_rate=0.5)
def summary(window_hours: float = Query(1.0, gt=0.0, le=24.0)) -> SummaryOut:
    con = _connect()
    if con is None:
        return SummaryOut(window_hours=window_hours, features=[])
    try:
        cutoff_iso = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - window_hours * 3600.0)
        )
        try:
            rows = con.execute(
                """
                SELECT feature_id,
                       MAX(ts_utc) AS last_seen_utc,
                       COUNT(*) AS events_total,
                       SUM(CASE WHEN level IN ('error','fatal') THEN 1 ELSE 0 END) AS errors_1h
                FROM events
                WHERE ts_utc >= ? AND feature_id IS NOT NULL
                GROUP BY feature_id
                ORDER BY last_seen_utc DESC
                """,
                (cutoff_iso,),
            ).fetchall()
        except sqlite3.Error:
            return SummaryOut(window_hours=window_hours, features=[])

        out: list[FeatureSummary] = []
        for r in rows:
            fid = r["feature_id"]
            # crude p95 from the same window (sorted-pick to avoid a numpy dep)
            p95: Optional[float] = None
            try:
                durs = [
                    d[0]
                    for d in con.execute(
                        "SELECT duration_ms FROM events "
                        "WHERE feature_id = ? AND ts_utc >= ? AND duration_ms IS NOT NULL "
                        "ORDER BY duration_ms ASC",
                        (fid, cutoff_iso),
                    ).fetchall()
                    if d[0] is not None
                ]
                if durs:
                    idx = max(0, int(round(0.95 * (len(durs) - 1))))
                    p95 = float(durs[idx])
            except sqlite3.Error:
                p95 = None
            out.append(
                FeatureSummary(
                    feature_id=fid,
                    last_seen_utc=r["last_seen_utc"],
                    events_total=int(r["events_total"]),
                    errors_1h=int(r["errors_1h"] or 0),
                    p95_duration_ms=p95,
                )
            )
        return SummaryOut(window_hours=window_hours, features=out)
    finally:
        con.close()


@router.get("/silent", response_model=SilentOut, dependencies=[Depends(require_auth)])
@trace("obs.events", sample_rate=0.5)
def silent(
    minutes: int = Query(15, ge=1, le=24 * 60),
    expected: Optional[str] = Query(
        None,
        description="Comma-separated feature_ids that should be alive. If omitted, "
        "we use every feature_id seen in the last 24h as the baseline.",
    ),
) -> SilentOut:
    con = _connect()
    if con is None:
        return SilentOut(silent_for_minutes=minutes, features=[])
    try:
        cutoff_iso = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes * 60.0)
        )
        try:
            recent = {
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT feature_id FROM events "
                    "WHERE ts_utc >= ? AND feature_id IS NOT NULL",
                    (cutoff_iso,),
                ).fetchall()
            }
        except sqlite3.Error:
            return SilentOut(silent_for_minutes=minutes, features=[])

        if expected:
            baseline = {s.strip() for s in expected.split(",") if s.strip()}
        else:
            day_ago = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 24 * 3600.0)
            )
            try:
                baseline = {
                    r[0]
                    for r in con.execute(
                        "SELECT DISTINCT feature_id FROM events "
                        "WHERE ts_utc >= ? AND feature_id IS NOT NULL",
                        (day_ago,),
                    ).fetchall()
                }
            except sqlite3.Error:
                baseline = set()

        missing = sorted(baseline - recent)
        return SilentOut(silent_for_minutes=minutes, features=missing)
    finally:
        con.close()


@router.get("/stats", response_model=StatsOut, dependencies=[Depends(require_auth)])
@trace("obs.events", sample_rate=0.1)
def stats() -> StatsOut:
    return StatsOut(
        db_exists=_DB_PATH.exists(),
        db_path=str(_DB_PATH),
        counters=_obs.get_stats(),
    )
