#!/usr/bin/env python3
"""gen_openapi_overlay.py — merge feature metadata into FastAPI's openapi.json.

We don't replace FastAPI's spec — it already does the heavy lifting from type
hints. Instead we overlay:

* tags = feature names, in stable order
* per-path tag assignment based on entrypoints in hosaka.features.yaml
* x-feature-id extension on each tagged operation

Run after `python scripts/dump_openapi.py` (or any tool that writes
docs/openapi.json) to enrich the spec.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _catalog import REPO_ROOT, load_catalog  # noqa: E402

DEFAULT_SPEC = REPO_ROOT / "docs" / "openapi.json"


def overlay(spec: dict, catalog: dict) -> tuple[dict, dict]:
    features = catalog.get("features", [])
    # tag list (deduped, ordered by category then id)
    tags: list[dict] = []
    seen: set[str] = set()
    for f in sorted(features, key=lambda x: (x.get("category", "z"), x.get("id", ""))):
        tag = f.get("name") or f.get("id")
        if tag in seen:
            continue
        seen.add(tag)
        tags.append({"name": tag, "description": (f.get("description") or "").strip()})
    spec["tags"] = tags

    # path-level overlay
    method_path_to_feature: dict[tuple[str, str], dict] = {}
    for f in features:
        for ep in f.get("entrypoints") or []:
            if ep.get("type") != "http":
                continue
            method = (ep.get("method") or "GET").lower()
            path = ep.get("path") or ""
            method_path_to_feature[(method, path)] = f

    paths = spec.get("paths") or {}
    matched = 0
    unmatched_in_catalog: list[str] = []
    for path, methods in paths.items():
        for method, op in (methods or {}).items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            f = method_path_to_feature.get((method, path))
            if not f:
                continue
            tag = f.get("name") or f.get("id")
            op.setdefault("tags", [])
            if tag not in op["tags"]:
                op["tags"].append(tag)
            op["x-feature-id"] = f["id"]
            matched += 1

    # Find catalog entries whose declared HTTP entrypoint is missing in the spec.
    spec_pairs = {
        (m, p)
        for p, ms in paths.items()
        for m in (ms or {})
        if m in {"get", "post", "put", "delete", "patch"}
    }
    for (m, p), f in method_path_to_feature.items():
        if (m, p) not in spec_pairs:
            unmatched_in_catalog.append(f"{m.upper()} {p} ({f['id']})")

    report = {
        "tags_written": len(tags),
        "operations_tagged": matched,
        "catalog_entrypoints_missing_in_spec": sorted(unmatched_in_catalog),
    }
    return spec, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(DEFAULT_SPEC))
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if catalog declares routes the spec doesn't have")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"[gen_openapi_overlay] no spec at {spec_path}; skip "
              "(run scripts/dump_openapi.py first)", file=sys.stderr)
        return 0
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[gen_openapi_overlay] bad json: {exc}", file=sys.stderr)
        return 1

    spec, report = overlay(spec, load_catalog())
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.strict and report["catalog_entrypoints_missing_in_spec"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
