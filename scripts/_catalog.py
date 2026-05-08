"""Shared loader for docs/hosaka.features.yaml.

Stdlib-only YAML parser is too painful, so we depend on PyYAML which is
already in the venv. If yaml isn't installed, the loader returns an empty
catalog and emits a warning — generators degrade to no-ops, never crash.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "docs" / "hosaka.features.yaml"


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"manifest_version": "0", "categories": {}, "features": []}
    try:
        import yaml  # type: ignore
    except ImportError:
        print(f"[catalog] PyYAML not installed; cannot read {path}", flush=True)
        return {"manifest_version": "0", "categories": {}, "features": []}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"[catalog] YAML error in {path}: {exc}", flush=True)
        return {"manifest_version": "0", "categories": {}, "features": []}
    data.setdefault("categories", {})
    data.setdefault("features", [])
    return data


def features_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in catalog.get("features", []) if f.get("id")}


def features_by_category(catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for f in catalog.get("features", []):
        cat = f.get("category", "uncategorized")
        out.setdefault(cat, []).append(f)
    return out


__all__ = [
    "REPO_ROOT",
    "CATALOG_PATH",
    "load_catalog",
    "features_by_id",
    "features_by_category",
]
