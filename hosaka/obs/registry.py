"""hosaka.obs.registry — in-process feature registry with @feature decorators.

Two ways to register a feature:

1) Declarative (YAML) — `docs/hosaka.features.yaml`. Stable, machine-readable,
   the source of truth for the manual + agent context + openapi tags.

2) In-code (decorators) — `@feature(...)` on a class or function, plus
   `@subfeature(...)` for child capabilities. Useful for plugins / experimental
   features that don't yet warrant a YAML entry.

Both populate the SAME registry. `reconcile_with_yaml()` is run by the
generators to fail-loud when in-code features and YAML disagree.

Hard rules (per docs/increased_observability.yaml):

* Decorators NEVER raise. Bad metadata logs a warning and returns the
  undecorated function.
* The registry is in-memory only — it doesn't write to disk.
* Decorators auto-attach @trace(feature_id) so registered functions
  automatically emit lifecycle events.
"""
from __future__ import annotations

import threading
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from hosaka.obs import emit, trace

# ── data ─────────────────────────────────────────────────────────────────────


@dataclass
class FeatureRecord:
    id: str
    name: str
    category: str = "uncategorized"
    description: str = ""
    owner: str = "unknown"
    status: str = "experimental"
    commands: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    baller_command: str = ""
    why_you_care: str = ""
    source: str = "code"  # "code" | "yaml"
    parent_id: Optional[str] = None
    callable_qualname: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "owner": self.owner,
            "status": self.status,
            "commands": list(self.commands),
            "permissions": list(self.permissions),
            "baller_command": self.baller_command,
            "why_you_care": self.why_you_care,
            "source": self.source,
            "parent_id": self.parent_id,
            "callable": self.callable_qualname,
        }


_lock = threading.Lock()
_registry: dict[str, FeatureRecord] = {}


# ── public API ───────────────────────────────────────────────────────────────


def register(record: FeatureRecord) -> bool:
    """Insert/replace a record. Returns True if newly added or updated."""
    try:
        with _lock:
            existed = record.id in _registry
            _registry[record.id] = record
        emit(
            "FEATURE_REGISTERED" if not existed else "FEATURE_UPDATED",
            kind="module",
            feature_id=record.id,
            source="hosaka.obs.registry",
            level="info",
            payload={"source": record.source, "status": record.status},
        )
        return True
    except Exception:
        return False


def get(feature_id: str) -> Optional[FeatureRecord]:
    with _lock:
        return _registry.get(feature_id)


def all_records() -> list[FeatureRecord]:
    with _lock:
        return list(_registry.values())


def clear() -> None:
    """For tests only."""
    with _lock:
        _registry.clear()


# ── decorators ───────────────────────────────────────────────────────────────


def feature(
    feature_id: str,
    *,
    name: Optional[str] = None,
    category: str = "uncategorized",
    description: str = "",
    owner: str = "unknown",
    status: str = "experimental",
    commands: Optional[list[str]] = None,
    permissions: Optional[list[str]] = None,
    baller_command: str = "",
    why_you_care: str = "",
    sample_rate: float = 1.0,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function/class as the entrypoint for a feature.

    Auto-applies @trace(feature_id) so the function emits lifecycle events.
    Safe to call at import time; never raises.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        try:
            qualname = f"{getattr(fn, '__module__', '?')}:{getattr(fn, '__qualname__', fn.__name__)}"
            record = FeatureRecord(
                id=feature_id,
                name=name or feature_id,
                category=category,
                description=description.strip(),
                owner=owner,
                status=status,
                commands=list(commands or []),
                permissions=list(permissions or []),
                baller_command=baller_command,
                why_you_care=why_you_care.strip(),
                source="code",
                callable_qualname=qualname,
            )
            register(record)
            wrapped = trace(feature_id, sample_rate=sample_rate)(fn)
            wrapped.__hosaka_feature_id__ = feature_id  # type: ignore[attr-defined]
            return wrapped
        except Exception as exc:
            warnings.warn(f"@feature({feature_id}) failed: {exc}", RuntimeWarning)
            return fn

    return decorator


def subfeature(
    parent_id: str,
    sub_id: str,
    *,
    name: Optional[str] = None,
    description: str = "",
    sample_rate: float = 1.0,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as a sub-capability of an existing feature.

    The full id becomes `<parent_id>.<sub_id>`. Inherits owner/category/status
    from the parent if it's already registered, else falls back to defaults.
    """

    full_id = f"{parent_id}.{sub_id}"

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        try:
            parent = get(parent_id)
            qualname = f"{getattr(fn, '__module__', '?')}:{getattr(fn, '__qualname__', fn.__name__)}"
            record = FeatureRecord(
                id=full_id,
                name=name or full_id,
                category=parent.category if parent else "uncategorized",
                description=description.strip(),
                owner=parent.owner if parent else "unknown",
                status=parent.status if parent else "experimental",
                source="code",
                parent_id=parent_id,
                callable_qualname=qualname,
            )
            register(record)
            wrapped = trace(full_id, sample_rate=sample_rate)(fn)
            wrapped.__hosaka_feature_id__ = full_id  # type: ignore[attr-defined]
            return wrapped
        except Exception as exc:
            warnings.warn(f"@subfeature({full_id}) failed: {exc}", RuntimeWarning)
            return fn

    return decorator


# ── reconciliation with YAML catalog ─────────────────────────────────────────


def hydrate_from_catalog(catalog: dict[str, Any]) -> int:
    """Seed the registry from a parsed hosaka.features.yaml.

    Returns the number of records added. Code-registered records are NOT
    overwritten — they win, because they reflect what the running process
    actually exposes.
    """
    added = 0
    for f in catalog.get("features", []) or []:
        fid = f.get("id")
        if not fid:
            continue
        with _lock:
            if fid in _registry and _registry[fid].source == "code":
                continue
        rec = FeatureRecord(
            id=fid,
            name=f.get("name", fid),
            category=f.get("category", "uncategorized"),
            description=(f.get("description") or "").strip(),
            owner=f.get("owner", "unknown"),
            status=f.get("status", "stable"),
            commands=list(f.get("commands") or []),
            permissions=list(f.get("permissions") or []),
            baller_command=(f.get("baller_command") or "").strip(),
            why_you_care=(f.get("why_you_care") or "").strip(),
            source="yaml",
        )
        register(rec)
        added += 1
    return added


def reconcile_with_yaml(catalog: dict[str, Any]) -> dict[str, list[str]]:
    """Compare in-process @feature/@subfeature records against the YAML catalog.

    Returns a dict with three buckets:
      - in_code_only   : ids decorated in code but missing from YAML
      - in_yaml_only   : ids in YAML but no decorator found
      - status_mismatch: ids where the two disagree on status

    Generators / CI use this to nudge developers to keep the catalog in sync.
    """
    yaml_ids = {f["id"]: f for f in (catalog.get("features") or []) if f.get("id")}
    with _lock:
        code_ids = {r.id: r for r in _registry.values() if r.source == "code"}

    in_code_only = sorted(set(code_ids) - set(yaml_ids))
    in_yaml_only = sorted(set(yaml_ids) - set(code_ids))
    status_mismatch: list[str] = []
    for fid in set(code_ids) & set(yaml_ids):
        if code_ids[fid].status != yaml_ids[fid].get("status"):
            status_mismatch.append(
                f"{fid}: code={code_ids[fid].status} yaml={yaml_ids[fid].get('status')}"
            )

    return {
        "in_code_only": in_code_only,
        "in_yaml_only": in_yaml_only,
        "status_mismatch": sorted(status_mismatch),
    }


__all__ = [
    "FeatureRecord",
    "feature",
    "subfeature",
    "register",
    "get",
    "all_records",
    "clear",
    "hydrate_from_catalog",
    "reconcile_with_yaml",
]
