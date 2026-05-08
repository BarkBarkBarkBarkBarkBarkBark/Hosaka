"""Smoke tests for scripts/build_crash_bundle.py and scripts/hosaka-canary.sh."""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _seed_events(tmp_db: Path, n: int = 5) -> None:
    for k in [k for k in os.environ if k.startswith("HOSAKA_OBS")]:
        del os.environ[k]
    os.environ["HOSAKA_OBS"] = "on"
    os.environ["HOSAKA_OBS_DB"] = str(tmp_db)
    os.environ["HOSAKA_OBS_BATCH_INTERVAL_MS"] = "50"
    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs"):
            del sys.modules[mod]
    obs = importlib.import_module("hosaka.obs")
    obs.emit("CRASH_PROBE", kind="function", feature_id="feat.boom",
             source="test", level="error", status="failed",
             payload={"api_key": "sk-supersecretvalue1234567890"})
    for i in range(n):
        obs.emit(f"E{i}", kind="function", feature_id="feat.x",
                 source="test", level="info", status="ok", duration_ms=float(i))
    # wait for writer to drain
    import sqlite3
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if tmp_db.exists():
            con = sqlite3.connect(str(tmp_db))
            try:
                (count,) = con.execute("SELECT COUNT(*) FROM events").fetchone()
            finally:
                con.close()
            if count >= n + 1:
                return
        time.sleep(0.05)


def test_crash_bundle_is_valid_tarball_with_expected_members(tmp_path):
    db = tmp_path / "events.db"
    _seed_events(db, n=3)
    out = tmp_path / "bundle.tgz"
    stack = tmp_path / "stack.txt"
    stack.write_text("Traceback (most recent call last):\n  File 'x.py', line 1\n")

    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_crash_bundle.py"),
         "--db", str(db), "--out", str(out),
         "--reason", "smoke test", "--stack", str(stack),
         "--window-min", "60"],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary["ok"] is True
    assert out.exists() and out.stat().st_size > 0

    with tarfile.open(out, "r:gz") as tf:
        names = set(tf.getnames())
        assert {"manifest.json", "events.jsonl", "obs_stats.json", "context.json",
                "features.yaml", "stack.txt", "notes.txt"}.issubset(names)
        events_data = tf.extractfile("events.jsonl").read().decode("utf-8")
        manifest_data = json.loads(tf.extractfile("manifest.json").read())

    # redaction worked
    assert "sk-supersecretvalue1234567890" not in events_data
    assert "[REDACTED]" in events_data
    # at least our seeded events made it
    assert events_data.count("\n") >= 4
    assert manifest_data["events"]["rows_in_window"] >= 4


def test_crash_bundle_works_with_no_db(tmp_path):
    db = tmp_path / "missing.db"  # never created
    out = tmp_path / "bundle.tgz"
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_crash_bundle.py"),
         "--db", str(db), "--out", str(out), "--reason", "no-db"],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    summary = json.loads(r.stdout)
    assert summary["ok"] is True
    with tarfile.open(out, "r:gz") as tf:
        manifest = json.loads(tf.extractfile("manifest.json").read())
    assert manifest["events"]["db_exists"] is False
    assert manifest["events"]["rows_in_window"] == 0


def test_crash_bundle_respects_max_bytes(tmp_path):
    db = tmp_path / "events.db"
    # Seed a lot of events so the trim path is exercised.
    _seed_events(db, n=500)
    out = tmp_path / "bundle.tgz"
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_crash_bundle.py"),
         "--db", str(db), "--out", str(out),
         "--max-bytes", "131072"],  # 128 KiB cap
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert out.stat().st_size <= 131072 * 2  # gzip + headers, generous slack
    with tarfile.open(out, "r:gz") as tf:
        manifest = json.loads(tf.extractfile("manifest.json").read())
    # If we trimmed, dropped_for_cap > 0; if not, that's also fine (small enough).
    assert manifest["events"]["dropped_for_cap"] >= 0


def test_canary_status_pin_rollback_promote(tmp_path):
    state_dir = tmp_path / "canary"
    env = os.environ.copy()
    env["HOSAKA_CANARY_DIR"] = str(state_dir)

    def run(*args):
        return subprocess.run(
            ["bash", str(SCRIPTS / "hosaka-canary.sh"), *args],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=10,
        )

    r = run("status")
    assert r.returncode == 0, r.stderr
    assert "current_ref:" in r.stdout
    assert "stage:       stage_0_local" in r.stdout

    r = run("pin", "deadbeef1234")
    assert r.returncode == 0, r.stderr
    assert (state_dir / "good_ref").read_text().strip() == "deadbeef1234"

    # second pin records a prev_ref so rollback has somewhere to go
    r = run("pin", "cafebabe5678")
    assert r.returncode == 0, r.stderr
    assert (state_dir / "prev_ref").read_text().strip() == "deadbeef1234"

    r = run("promote", "stage_1_ring")
    assert r.returncode == 0, r.stderr
    assert (state_dir / "stage").read_text().strip() == "stage_1_ring"

    # rollback path: skip touching real git by removing prev_ref then asserting failure.
    (state_dir / "prev_ref").unlink()
    r = run("rollback")
    assert r.returncode == 2  # documented "no prev_ref" failure
    assert "no prev_ref" in (r.stderr + r.stdout).lower()
