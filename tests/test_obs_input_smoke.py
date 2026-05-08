"""Smoke tests for hosaka.obs.input — keystroke / command / UI helpers."""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def _reload(tmp_path: Path, **env: str):
    db = tmp_path / "events.db"
    for k in [k for k in os.environ if k.startswith("HOSAKA_OBS")]:
        del os.environ[k]
    os.environ["HOSAKA_OBS"] = "on"
    os.environ["HOSAKA_OBS_DB"] = str(db)
    os.environ["HOSAKA_OBS_BATCH_INTERVAL_MS"] = "50"
    for k, v in env.items():
        os.environ[k] = v
    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs"):
            del sys.modules[mod]
    obs = importlib.import_module("hosaka.obs")
    obs_input = importlib.import_module("hosaka.obs.input")
    return obs, obs_input, db


def _wait_rows(db: Path, n: int, timeout: float = 3.0) -> bool:
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


def test_keystroke_records_normalized_key(tmp_path):
    _, obs_input, db = _reload(tmp_path)
    assert obs_input.record_keystroke("Enter", context="prompt") is True
    assert obs_input.record_keystroke("a", context="prompt", buffer_len=3) is True
    assert _wait_rows(db, 2)

    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT payload_json FROM events WHERE kind='keystroke' ORDER BY id ASC"
        ).fetchall()
    finally:
        con.close()
    payloads = [json.loads(r[0]) for r in rows]
    keys = [p.get("payload", {}).get("key") for p in payloads]
    assert "Enter" in keys
    assert "printable" in keys  # single-char keys are normalized


def test_keystroke_in_secret_context_drops_key_name(tmp_path):
    _, obs_input, db = _reload(tmp_path)
    obs_input.record_keystroke("p", context="secret", buffer_len=5)
    assert _wait_rows(db, 1)
    con = sqlite3.connect(str(db))
    try:
        (raw,) = con.execute("SELECT payload_json FROM events").fetchone()
    finally:
        con.close()
    payload = json.loads(raw).get("payload", {})
    assert "key" not in payload
    assert payload.get("buffer_len") == 5
    assert payload.get("context") == "secret"


def test_keystrokes_off_disables_helper_but_not_emit(tmp_path):
    obs, obs_input, db = _reload(tmp_path, HOSAKA_OBS_KEYSTROKES="off")
    assert obs_input.record_keystroke("x") is False
    # Other emits still work
    assert obs.emit("OTHER", source="test") is True
    assert _wait_rows(db, 1)


def test_command_submission_records_command_line(tmp_path):
    _, obs_input, db = _reload(tmp_path)
    obs_input.record_command_submission("hosaka mode device", feature_id="device.mode")
    assert _wait_rows(db, 1)
    con = sqlite3.connect(str(db))
    try:
        (kind, fid, raw) = con.execute(
            "SELECT kind, feature_id, payload_json FROM events"
        ).fetchone()
    finally:
        con.close()
    assert kind == "command"
    assert fid == "device.mode"
    p = json.loads(raw).get("payload", {})
    assert p.get("command_line") == "hosaka mode device"


def test_command_submission_in_secret_context_only_records_length(tmp_path):
    _, obs_input, db = _reload(tmp_path)
    obs_input.record_command_submission("hunter2-secret", context="password")
    assert _wait_rows(db, 1)
    con = sqlite3.connect(str(db))
    try:
        (raw,) = con.execute("SELECT payload_json FROM events").fetchone()
    finally:
        con.close()
    p = json.loads(raw).get("payload", {})
    assert "command_line" not in p
    assert p.get("length") == len("hunter2-secret")


def test_ui_event_records_route_and_target(tmp_path):
    _, obs_input, db = _reload(tmp_path)
    obs_input.record_ui_event(
        "FEATURE_INVOKED",
        feature_id="device.health",
        route="/device",
        target="health-card",
    )
    assert _wait_rows(db, 1)
    con = sqlite3.connect(str(db))
    try:
        (kind, fid, raw) = con.execute(
            "SELECT kind, feature_id, payload_json FROM events"
        ).fetchone()
    finally:
        con.close()
    assert kind == "ui"
    assert fid == "device.health"
    p = json.loads(raw).get("payload", {})
    assert p.get("route") == "/device"
    assert p.get("target") == "health-card"
