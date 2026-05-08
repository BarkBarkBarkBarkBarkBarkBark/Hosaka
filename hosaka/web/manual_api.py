"""hosaka.web.manual_api — serve generated manual + suggestions over HTTP.

Endpoints:

    GET /api/v1/manual                     index (list of features)
    GET /api/v1/manual/{feature_id}        one feature page (markdown)
    GET /api/v1/suggest?q=...              "did you mean?" for an unknown command
    GET /api/v1/features                   the registry as JSON

Same auth model as the rest of api_v1. Read-only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from hosaka.obs import heartbeat, trace
from hosaka.obs.suggest import known_commands, suggest_for
from hosaka.web.api_v1 import require_auth

router = APIRouter(prefix="/api/v1", tags=["manual"])
heartbeat("hosaka.web.manual_api")()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANUAL_DIR = Path(os.getenv("HOSAKA_MANUAL_DIR", str(_REPO_ROOT / "docs" / "manual")))
_AGENT_CTX = Path(os.getenv("HOSAKA_AGENT_CTX", str(_REPO_ROOT / "docs" / "agent_context.json")))
_FEATURES_YAML = Path(
    os.getenv("HOSAKA_FEATURES_YAML", str(_REPO_ROOT / "docs" / "hosaka.features.yaml"))
)


class SuggestOut(BaseModel):
    input: str
    did_you_mean: Optional[str] = None
    feature_id: Optional[str] = None
    manual_url: Optional[str] = None
    api_docs_url: Optional[str] = None
    message: str


class FeatureSummaryOut(BaseModel):
    id: str
    name: str
    category: str
    status: str
    baller_command: str = ""
    why_you_care: str = ""
    manual_url: str


class FeaturesListOut(BaseModel):
    count: int
    features: list[FeatureSummaryOut]


@router.get("/suggest", response_model=SuggestOut, dependencies=[Depends(require_auth)])
@trace("manual", sample_rate=0.5)
def suggest(q: str = Query(..., min_length=1, max_length=256)) -> SuggestOut:
    s = suggest_for(q)
    return SuggestOut(**s.to_dict())


@router.get("/manual", response_model=FeaturesListOut, dependencies=[Depends(require_auth)])
@trace("manual", sample_rate=0.5)
def manual_index() -> FeaturesListOut:
    if not _AGENT_CTX.exists():
        return FeaturesListOut(count=0, features=[])
    try:
        ctx: dict[str, Any] = json.loads(_AGENT_CTX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return FeaturesListOut(count=0, features=[])
    # also load the features.yaml for richer fields
    catalog_path = _FEATURES_YAML
    features_yaml: list[dict[str, Any]] = []
    if catalog_path.exists():
        try:
            import yaml  # type: ignore

            features_yaml = (yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}).get(
                "features", []
            )
        except Exception:
            features_yaml = []
    out: list[FeatureSummaryOut] = []
    for f in features_yaml:
        fid = f.get("id")
        if not fid:
            continue
        out.append(
            FeatureSummaryOut(
                id=fid,
                name=f.get("name", fid),
                category=f.get("category", "uncategorized"),
                status=f.get("status", "stable"),
                baller_command=(f.get("baller_command") or "").strip(),
                why_you_care=(f.get("why_you_care") or "").strip(),
                manual_url=f"/api/v1/manual/{fid}",
            )
        )
    out.sort(key=lambda x: (x.category, x.id))
    return FeaturesListOut(count=len(out), features=out)


@router.get(
    "/manual/{feature_id}",
    response_class=PlainTextResponse,
    dependencies=[Depends(require_auth)],
)
@trace("manual", sample_rate=0.5)
def manual_page(feature_id: str) -> str:
    # path-traversal guard
    if "/" in feature_id or ".." in feature_id:
        raise HTTPException(status_code=400, detail="invalid feature id")
    page = _MANUAL_DIR / f"{feature_id}.md"
    if not page.exists():
        s = suggest_for(feature_id)
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"no manual page for '{feature_id}'",
                "suggestion": s.to_dict(),
            },
        )
    try:
        return page.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"could not read page: {exc}")


@router.get("/features", dependencies=[Depends(require_auth)])
@trace("manual", sample_rate=0.5)
def features() -> dict[str, Any]:
    """Return the agent_context.json as the canonical features JSON."""
    if not _AGENT_CTX.exists():
        return {"schema_version": "0", "features": [], "known_commands": known_commands()}
    try:
        ctx = json.loads(_AGENT_CTX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        ctx = {}
    ctx["known_commands"] = known_commands()
    return ctx
