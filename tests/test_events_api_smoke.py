"""End-to-end smoke for /api/v1/events using FastAPI TestClient.

Boots the events router in isolation against a tmp DB, emits some events,
and asserts the read endpoints behave.
"""
from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _wait_rows(db: Path, n: int, timeout: float = 3.0) -> bool:
    import sqlite3

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if db.exists():
            try:
                con = sqlite3.connect(str(db))
                try:
                    (count,) = con.execute("SELECT COUNT(*) FROM events").fetchone()
                finally:
                    con.close()
                if count >= n:
                    return True
            except Exception:
                pass
        time.sleep(0.05)
    return False


def _boot(tmp_path: Path) -> tuple[TestClient, "object"]:
    db = tmp_path / "events.db"
    for k in [k for k in os.environ if k.startswith("HOSAKA_OBS")]:
        del os.environ[k]
    os.environ["HOSAKA_OBS"] = "on"
    os.environ["HOSAKA_OBS_DB"] = str(db)
    os.environ["HOSAKA_OBS_BATCH_INTERVAL_MS"] = "50"

    # Force reload so module-level _DB_PATH picks up the env var.
    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs") or mod.startswith("hosaka.web.events_api"):
            del sys.modules[mod]

    obs = importlib.import_module("hosaka.obs")
    events_api = importlib.import_module("hosaka.web.events_api")
    app = FastAPI()
    app.include_router(events_api.router)
    client = TestClient(app)
    # All requests come from TestClient which is loopback (127.0.0.1) → no auth needed.
    return client, obs


def test_events_list_and_summary(tmp_path):
    client, obs = _boot(tmp_path)

    obs.emit("LAUNCH", kind="command", feature_id="feat.launch", source="test", level="info", status="ok", duration_ms=12.3)
    obs.emit("BOOM", kind="function", feature_id="feat.boom", source="test", level="error", status="failed", duration_ms=99.0)
    obs.emit("LAUNCH", kind="command", feature_id="feat.launch", source="test", level="info", status="ok", duration_ms=8.0)

    db = Path(os.environ["HOSAKA_OBS_DB"])
    assert _wait_rows(db, 3)

    # GET /
    r = client.get("/api/v1/events?limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 3
    assert {e["feature_id"] for e in body["events"]} >= {"feat.launch", "feat.boom"}

    # filter by feature
    r = client.get("/api/v1/events?feature_id=feat.boom")
    assert r.status_code == 200
    assert all(e["feature_id"] == "feat.boom" for e in r.json()["events"])

    # filter by level
    r = client.get("/api/v1/events?level=error")
    assert r.status_code == 200
    assert all(e["level"] == "error" for e in r.json()["events"])

    # summary
    r = client.get("/api/v1/events/summary?window_hours=1")
    assert r.status_code == 200
    feats = {f["feature_id"]: f for f in r.json()["features"]}
    assert "feat.launch" in feats and "feat.boom" in feats
    assert feats["feat.launch"]["events_total"] >= 2
    assert feats["feat.boom"]["errors_1h"] >= 1
    assert feats["feat.launch"]["p95_duration_ms"] is not None

    # stats
    r = client.get("/api/v1/events/stats")
    assert r.status_code == 200
    j = r.json()
    assert j["db_exists"] is True
    assert j["counters"]["written"] >= 3


def test_silent_endpoint_finds_features_with_no_recent_events(tmp_path):
    client, obs = _boot(tmp_path)

    # Seed an event for feat.alive
    obs.emit("ALIVE", kind="function", feature_id="feat.alive", source="test", level="info", status="ok")
    db = Path(os.environ["HOSAKA_OBS_DB"])
    assert _wait_rows(db, 1)

    # Ask: which of (feat.alive, feat.ghost) has been silent for the last 1 minute?
    r = client.get("/api/v1/events/silent?minutes=1&expected=feat.alive,feat.ghost")
    assert r.status_code == 200
    body = r.json()
    assert body["features"] == ["feat.ghost"]


def test_endpoints_safe_when_db_missing(tmp_path):
    # Boot pointing at a non-existent DB (don't emit anything).
    db = tmp_path / "nope.db"
    for k in [k for k in os.environ if k.startswith("HOSAKA_OBS")]:
        del os.environ[k]
    os.environ["HOSAKA_OBS"] = "on"
    os.environ["HOSAKA_OBS_DB"] = str(db)
    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs") or mod.startswith("hosaka.web.events_api"):
            del sys.modules[mod]
    events_api = importlib.import_module("hosaka.web.events_api")
    app = FastAPI()
    app.include_router(events_api.router)
    client = TestClient(app)

    for path in ("/api/v1/events", "/api/v1/events/summary", "/api/v1/events/silent", "/api/v1/events/stats"):
        r = client.get(path)
        assert r.status_code == 200, f"{path}: {r.text}"
