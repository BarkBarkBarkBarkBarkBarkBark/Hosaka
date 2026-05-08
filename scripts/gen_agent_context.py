#!/usr/bin/env python3
"""gen_agent_context.py — generate docs/agent_context.json.

Goal: every future Copilot/Claude session can read ONE small JSON to know:
* what features exist, with status + owner
* where logs live, where the catalog lives, what NOT to touch
* which entrypoints (HTTP, scripts) map to which feature

The hand-written docs/AGENT_CONTEXT.md remains the human seed; this JSON is
the machine seed. Both point at the same catalog.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _catalog import REPO_ROOT, load_catalog  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "docs" / "agent_context.json"


def build_context(catalog: dict) -> dict:
    features = catalog.get("features", [])
    by_status: dict[str, list[str]] = {}
    by_category: dict[str, list[str]] = {}
    http_routes: list[dict] = []
    scripts: list[dict] = []
    for f in features:
        fid = f["id"]
        by_status.setdefault(f.get("status", "stable"), []).append(fid)
        by_category.setdefault(f.get("category", "uncategorized"), []).append(fid)
        for ep in f.get("entrypoints", []) or []:
            if ep.get("type") == "http":
                http_routes.append(
                    {
                        "method": ep.get("method", "GET"),
                        "path": ep.get("path", ""),
                        "feature_id": fid,
                    }
                )
            elif ep.get("type") == "script":
                scripts.append({"path": ep.get("path", ""), "feature_id": fid})

    return {
        "schema_version": "1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "single_source_of_truth": "Hosaka/docs/hosaka.features.yaml",
        "human_seed": "Hosaka/docs/AGENT_CONTEXT.md",
        "plan": "Hosaka/docs/increased_observability.yaml",
        "event_store": {
            "path": "Hosaka/runtime/observability/events.db",
            "engine": "sqlite-wal",
            "retention_hours": 24,
            "read_api": [
                "GET /api/v1/events",
                "GET /api/v1/events/summary",
                "GET /api/v1/events/silent",
                "GET /api/v1/events/stats",
            ],
        },
        "obs_library": {
            "import": "from hosaka.obs import emit, trace, heartbeat",
            "guarantees": [
                "never raises",
                "supervised writer thread",
                "bounded queue (4096) and payload (4 KiB)",
                "disabling via HOSAKA_OBS=off is a true no-op",
            ],
        },
        "catalog_summary": {
            "total_features": len(features),
            "by_status": by_status,
            "by_category": by_category,
        },
        "http_routes": sorted(http_routes, key=lambda r: r["path"]),
        "scripts": sorted(scripts, key=lambda r: r["path"]),
        "hard_nos": [
            "no new long-running processes",
            "no editing docs/openapi.json or docs/manual/** by hand",
            "no removing features (mark status=deprecated)",
            "no telemetry that can throw",
            "no ORM, no migration framework inside hosaka.obs",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    ctx = build_context(load_catalog())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ctx, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"[gen_agent_context] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
