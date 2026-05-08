"""Smoke tests for the doc generators."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _run(cmd: list[str], cwd: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)


def test_gen_user_manual_writes_index_and_per_feature_pages(tmp_path):
    out = tmp_path / "manual"
    r = _run([sys.executable, str(SCRIPTS / "gen_user_manual.py"), "--out", str(out),
              "--include-internal"])
    assert r.returncode == 0, r.stderr
    assert (out / "index.md").exists()
    text = (out / "index.md").read_text()
    assert text.startswith("<!-- GENERATED")
    assert "## observability" in text
    assert "/events recent" in text
    # every feature has a page
    import yaml  # noqa
    catalog = yaml.safe_load((REPO / "docs" / "hosaka.features.yaml").read_text())
    for f in catalog["features"]:
        page = out / f"{f['id']}.md"
        assert page.exists(), f"missing page for {f['id']}"
        body = page.read_text()
        assert f.get("name", f["id"]) in body
        if f.get("baller_command"):
            assert f["baller_command"] in body


def test_gen_agent_context_writes_valid_json(tmp_path):
    out = tmp_path / "agent_context.json"
    r = _run([sys.executable, str(SCRIPTS / "gen_agent_context.py"), "--out", str(out)])
    assert r.returncode == 0, r.stderr
    ctx = json.loads(out.read_text())
    assert ctx["schema_version"] == "1"
    assert ctx["single_source_of_truth"].endswith("hosaka.features.yaml")
    assert ctx["catalog_summary"]["total_features"] >= 4
    paths = {r["path"] for r in ctx["http_routes"]}
    assert "/api/v1/events" in paths
    assert "/api/v1/health" in paths


def test_gen_openapi_overlay_tags_known_routes(tmp_path):
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "test", "version": "1"},
        "paths": {
            "/api/v1/events": {"get": {"summary": "list events", "responses": {"200": {}}}},
            "/api/v1/health": {"get": {"summary": "health", "responses": {"200": {}}}},
            "/api/v1/unknown": {"get": {"summary": "untagged", "responses": {"200": {}}}},
        },
    }
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps(spec))

    r = _run([sys.executable, str(SCRIPTS / "gen_openapi_overlay.py"), "--spec", str(spec_path)])
    assert r.returncode == 0, r.stderr

    out = json.loads(spec_path.read_text())
    assert "tags" in out and len(out["tags"]) >= 4
    ev = out["paths"]["/api/v1/events"]["get"]
    assert "tags" in ev and any("event" in t.lower() for t in ev["tags"])
    assert ev.get("x-feature-id") == "obs.events"
    # Routes not in catalog stay untouched
    assert "x-feature-id" not in out["paths"]["/api/v1/unknown"]["get"]


def test_gen_openapi_overlay_strict_flags_missing_routes(tmp_path):
    spec = {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "paths": {}}
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps(spec))
    r = _run([sys.executable, str(SCRIPTS / "gen_openapi_overlay.py"),
              "--spec", str(spec_path), "--strict"])
    # Catalog declares HTTP entrypoints that are missing from this empty spec → strict fail
    assert r.returncode == 2, r.stderr or r.stdout
