"""Hosaka docs API — list / read / write / append markdown notes.

Single dedicated directory the operator (and the picoclaw agent) can both
write to. Path resolution order:

1. ``$HOSAKA_DOCS_DIR`` if set.
2. ``$PICOCLAW_HOME/.picoclaw/workspace/memory`` if ``PICOCLAW_HOME`` set.
3. ``~/.picoclaw/workspace/memory`` (default — picoclaw already writes here).
4. ``~/.hosaka/docs`` (fallback).

The directory is created on first use. All path inputs are resolved and
asserted to live under the root; traversal attempts return 400.

Mounted at ``/api/v1/docs`` from :mod:`hosaka.web.server`.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/docs", tags=["docs"])


# ── storage location ────────────────────────────────────────────────────


def docs_root() -> Path:
    """Return (and create if missing) the docs directory."""
    explicit = os.getenv("HOSAKA_DOCS_DIR")
    if explicit:
        root = Path(explicit).expanduser()
    else:
        picoclaw_home = os.getenv("PICOCLAW_HOME")
        if picoclaw_home:
            root = Path(picoclaw_home).expanduser() / ".picoclaw" / "workspace" / "memory"
        else:
            candidate = Path.home() / ".picoclaw" / "workspace" / "memory"
            # If picoclaw isn't installed yet, fall back to ~/.hosaka/docs so
            # we never plant files inside a parent that doesn't make sense.
            if candidate.parent.exists() or candidate.exists():
                root = candidate
            else:
                root = Path.home() / ".hosaka" / "docs"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


# ── path safety ─────────────────────────────────────────────────────────


_SAFE_RE = re.compile(r"^[A-Za-z0-9._\- /]+$")


def _resolve(rel: str) -> Path:
    """Resolve ``rel`` under the docs root. Raises 400 on traversal."""
    rel = (rel or "").strip().lstrip("/")
    if not rel or rel in {".", ".."} or "\x00" in rel:
        raise HTTPException(status_code=400, detail="invalid path")
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=400, detail="path traversal not allowed")
    if not _SAFE_RE.match(rel):
        raise HTTPException(status_code=400, detail="path contains illegal characters")
    if not rel.endswith(".md"):
        rel = rel + ".md"
    root = docs_root()
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes docs root") from exc
    return target


# ── models ──────────────────────────────────────────────────────────────


class DocSummary(BaseModel):
    path: str
    size: int
    mtime: float
    title: str


class DocListResponse(BaseModel):
    root: str
    docs: list[DocSummary]


class DocReadResponse(BaseModel):
    path: str
    body: str
    mtime: float


class DocWriteRequest(BaseModel):
    path: str = Field(..., description="Relative path under docs root, .md auto-added.")
    body: str = Field("", description="File body. UTF-8.")
    mode: Literal["overwrite", "append"] = "overwrite"


class DocWriteResponse(BaseModel):
    ok: bool
    path: str
    bytes: int
    mtime: float
    spoken: str


class DocTemplateRequest(BaseModel):
    template: Literal["summary", "todo", "note"]
    slug: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


# ── helpers ─────────────────────────────────────────────────────────────


def _title_from(body: str, fallback: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()[:120]
        if s:
            return s[:120]
    return fallback


def _slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return text[:60] or "doc"


def _stamp_slug(slug: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{today}-{_slugify(slug)}.md"


def _render_template(req: DocTemplateRequest) -> tuple[str, str]:
    """Return (relative_path, body) for a template request."""
    title = (req.title or req.slug or req.template).strip() or req.template
    slug = req.slug or title
    rel = _stamp_slug(slug)
    iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    extra = (req.body or "").strip()
    if req.template == "summary":
        body = (
            f"# {title}\n\n"
            f"_summary · {iso}_\n\n"
            "## context\n\n"
            f"{extra or '...'}\n\n"
            "## key points\n\n- \n- \n- \n\n"
            "## next steps\n\n- [ ] \n- [ ] \n"
        )
    elif req.template == "todo":
        items = [l for l in (extra.splitlines() if extra else []) if l.strip()]
        if items:
            checks = "\n".join(f"- [ ] {l.strip().lstrip('- ').lstrip('* ')}" for l in items)
        else:
            checks = "- [ ] \n- [ ] \n- [ ] "
        body = f"# {title}\n\n_todo · {iso}_\n\n{checks}\n"
    else:  # note
        body = f"# {title}\n\n_note · {iso}_\n\n{extra or ''}\n"
    return rel, body


# ── endpoints ───────────────────────────────────────────────────────────


@router.get("", response_model=DocListResponse)
@router.get("/", response_model=DocListResponse, include_in_schema=False)
def list_docs() -> DocListResponse:
    root = docs_root()
    docs: list[DocSummary] = []
    for p in sorted(root.rglob("*.md")):
        try:
            stat = p.stat()
            head = ""
            try:
                with p.open("r", encoding="utf-8", errors="replace") as fh:
                    head = fh.read(512)
            except OSError:
                pass
            docs.append(
                DocSummary(
                    path=str(p.relative_to(root)),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    title=_title_from(head, p.stem),
                )
            )
        except OSError:
            continue
    # newest first
    docs.sort(key=lambda d: d.mtime, reverse=True)
    return DocListResponse(root=str(root), docs=docs)


@router.get("/file", response_model=DocReadResponse)
def read_doc(path: str) -> DocReadResponse:
    target = _resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="doc not found")
    try:
        body = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"read failed: {exc}") from exc
    return DocReadResponse(
        path=str(target.relative_to(docs_root())),
        body=body,
        mtime=target.stat().st_mtime,
    )


@router.put("/file", response_model=DocWriteResponse)
def write_doc(req: DocWriteRequest) -> DocWriteResponse:
    target = _resolve(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if req.mode == "append" and target.exists():
        prev = target.read_text(encoding="utf-8")
        sep = "" if prev.endswith("\n") else "\n"
        body = prev + sep + req.body
    else:
        body = req.body
    target.write_text(body, encoding="utf-8")
    rel = str(target.relative_to(docs_root()))
    return DocWriteResponse(
        ok=True,
        path=rel,
        bytes=len(body.encode("utf-8")),
        mtime=target.stat().st_mtime,
        spoken=f"saved {rel}",
    )


@router.post("/template", response_model=DocWriteResponse)
def write_template(req: DocTemplateRequest) -> DocWriteResponse:
    rel, body = _render_template(req)
    return write_doc(DocWriteRequest(path=rel, body=body, mode="overwrite"))


# ── shared helpers (consumed by hosaka.voice.tools) ─────────────────────


def list_docs_summary(limit: int = 30) -> list[dict]:
    resp = list_docs()
    return [d.model_dump() for d in resp.docs[:limit]]


def write_doc_simple(path: str, body: str, append: bool = False) -> dict:
    return write_doc(
        DocWriteRequest(path=path, body=body, mode="append" if append else "overwrite")
    ).model_dump()


def read_doc_simple(path: str) -> dict:
    return read_doc(path).model_dump()


def write_template_simple(template: str, slug: str | None = None, title: str | None = None, body: str | None = None) -> dict:
    return write_template(
        DocTemplateRequest(template=template, slug=slug, title=title, body=body)  # type: ignore[arg-type]
    ).model_dump()
