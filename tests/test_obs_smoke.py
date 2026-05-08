"""Smoke tests for hosaka.obs.

These tests enforce the hard contract of phase 07/08:

* emit / decorators NEVER raise, no matter what we throw at them
* the writer thread is supervised (kill it, next emit revives it)
* retention drops old rows
* disabled mode short-circuits with no DB writes
* @trace wrapper preserves return value and re-raises business exceptions
* schema is additive: re-importing against an existing DB is fine
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


def _fresh_obs(tmp_path: Path, **env: str):
    """Reload hosaka.obs against a clean DB and a fresh module-state."""
    db = tmp_path / "events.db"
    # Reset the obs-related env so each test starts from a known state.
    for stale in [k for k in os.environ if k.startswith("HOSAKA_OBS")]:
        del os.environ[stale]
    os.environ["HOSAKA_OBS_DB"] = str(db)
    os.environ["HOSAKA_OBS"] = "on"
    for k, v in env.items():
        os.environ[k] = v
    if "hosaka.obs" in sys.modules:
        del sys.modules["hosaka.obs"]
    obs = importlib.import_module("hosaka.obs")
    return obs, db


def _wait_for(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _row_count(db: Path) -> int:
    if not db.exists():
        return 0
    con = sqlite3.connect(str(db))
    try:
        cur = con.execute("SELECT COUNT(*) FROM events")
        (n,) = cur.fetchone()
        return int(n)
    finally:
        con.close()


# ── basic plumbing ───────────────────────────────────────────────────────────


def test_emit_writes_and_persists(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")
    assert obs.emit("HELLO", kind="custom", source="test", level="info") is True
    assert _wait_for(lambda: _row_count(db) >= 1, timeout=3.0)
    stats = obs.get_stats()
    assert stats["emitted"] >= 1
    assert stats["written"] >= 1


def test_emit_never_raises_on_garbage_input(tmp_path):
    obs, _ = _fresh_obs(tmp_path)

    class Boom:
        def __repr__(self):
            raise RuntimeError("nope")

    # Pass un-serializable + un-stringifiable junk; must still return cleanly.
    result = obs.emit(
        "WEIRD",
        kind="custom",
        source="test",
        level="not-a-real-level",  # coerced to info
        payload=Boom(),
        weird_field=Boom(),
    )
    assert result in (True, False)  # the only thing we promise: no exception


def test_disabled_mode_is_no_op(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS="off")
    assert obs.emit("X", source="test") is False
    # Give the (non-existent) writer a moment, then assert no DB was created
    # AND no rows exist if it was.
    time.sleep(0.2)
    assert not db.exists() or _row_count(db) == 0
    assert obs.get_stats()["dropped_disabled"] >= 1


# ── @trace ───────────────────────────────────────────────────────────────────


def test_trace_records_success_and_returns_value(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")

    @obs.trace("test.feature.add")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5
    assert _wait_for(lambda: _row_count(db) >= 1)
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT kind, feature_id, status FROM events WHERE feature_id='test.feature.add'"
        ).fetchall()
    finally:
        con.close()
    assert any(r == ("function", "test.feature.add", "ok") for r in rows)


def test_trace_records_failure_and_reraises(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")

    @obs.trace("test.feature.boom")
    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        boom()

    assert _wait_for(lambda: _row_count(db) >= 1)
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT status, level FROM events WHERE feature_id='test.feature.boom'"
        ).fetchall()
    finally:
        con.close()
    assert any(r == ("failed", "error") for r in rows)


def test_trace_zero_sample_rate_is_cheap_and_silent(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")

    @obs.trace("test.feature.hot", sample_rate=0.0)
    def hot(x):
        return x * 2

    for i in range(1000):
        assert hot(i) == i * 2

    time.sleep(0.2)
    # No samples means no rows for this feature.
    con = sqlite3.connect(str(db)) if db.exists() else None
    if con is not None:
        try:
            (n,) = con.execute(
                "SELECT COUNT(*) FROM events WHERE feature_id='test.feature.hot'"
            ).fetchone()
        finally:
            con.close()
        assert n == 0


# ── @heartbeat ───────────────────────────────────────────────────────────────


def test_heartbeat_emits_module_loaded_once(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")
    beat = obs.heartbeat("test.module.alpha", interval_s=3600)
    beat()
    beat()  # within interval, must NOT emit again
    beat()
    assert _wait_for(lambda: _row_count(db) >= 1)
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT payload_json FROM events WHERE feature_id='test.module.alpha'"
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 1
    assert "MODULE_LOADED" in rows[0][0]


# ── supervision ──────────────────────────────────────────────────────────────


def test_writer_revives_after_being_killed(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")
    obs.emit("FIRST", source="test")
    assert _wait_for(lambda: _row_count(db) >= 1)

    # Kill the writer thread reference and signal nothing — just drop it.
    # _ensure_writer should spin up a fresh one on the next emit.
    import hosaka.obs as obs_mod  # type: ignore

    with obs_mod._writer_lock:  # type: ignore[attr-defined]
        obs_mod._writer_thread = None  # type: ignore[attr-defined]

    obs.emit("SECOND", source="test")
    assert _wait_for(lambda: _row_count(db) >= 2, timeout=3.0)


def test_queue_full_does_not_raise(tmp_path):
    obs, _ = _fresh_obs(
        tmp_path,
        HOSAKA_OBS_QUEUE_MAX="4",
        HOSAKA_OBS_BATCH_INTERVAL_MS="10000",  # writer parked, queue will fill
    )
    # Stop the writer from draining by not waiting; just hammer the queue.
    results = [obs.emit(f"E{i}", source="test") for i in range(200)]
    # We expect at least some Falses (queue full). None of them threw.
    assert any(r is False for r in results)
    assert obs.get_stats()["dropped_queue_full"] > 0


# ── retention ────────────────────────────────────────────────────────────────


def test_row_cap_evicts_oldest(tmp_path):
    obs, db = _fresh_obs(
        tmp_path,
        HOSAKA_OBS_BATCH_INTERVAL_MS="20",
        HOSAKA_OBS_ROW_CAP="50",
        HOSAKA_OBS_EVICT_EVERY="25",
    )
    for i in range(300):
        obs.emit(f"E{i}", source="test")
    # Wait for writer to drain + at least one eviction pass.
    assert _wait_for(lambda: _row_count(db) > 0, timeout=3.0)
    time.sleep(0.5)
    n = _row_count(db)
    # Must be capped, with some slack for the batch that triggered eviction.
    assert n <= 75, f"row cap not enforced: n={n}"


# ── schema is reusable ───────────────────────────────────────────────────────


def test_reopening_existing_db_is_safe(tmp_path):
    obs, db = _fresh_obs(tmp_path, HOSAKA_OBS_BATCH_INTERVAL_MS="50")
    obs.emit("ROUND1", source="test")
    assert _wait_for(lambda: _row_count(db) >= 1)
    obs._shutdown_writer(timeout=2.0)  # type: ignore[attr-defined]

    # Reload as if the process restarted; same DB path.
    if "hosaka.obs" in sys.modules:
        del sys.modules["hosaka.obs"]
    obs2 = importlib.import_module("hosaka.obs")
    obs2.emit("ROUND2", source="test")
    assert _wait_for(lambda: _row_count(db) >= 2)
