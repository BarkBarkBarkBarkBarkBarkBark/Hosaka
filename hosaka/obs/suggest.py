"""hosaka.obs.suggest — "did you mean?" + manual links for unknown commands.

When a user types something the system doesn't recognize, this module returns
a friendly nudge pointing at the right place:

    >>> suggest_for("/healht")
    Suggestion(input='/healht', did_you_mean='/health',
               feature_id='device.health',
               manual_url='/manual/device.health',
               api_docs_url='/api/v1/docs#tag/device-health',
               message="did you mean `/health`? see /manual/device.health")

Stdlib only (uses difflib). Never raises.
"""
from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── catalog loader (uses the same yaml file as everything else) ──────────────

_CATALOG_PATH = Path(
    os.getenv(
        "HOSAKA_FEATURES_YAML",
        str(Path(__file__).resolve().parents[2] / "docs" / "hosaka.features.yaml"),
    )
)
_BASE_MANUAL_URL = os.getenv("HOSAKA_MANUAL_URL_BASE", "/manual")
_BASE_API_DOCS_URL = os.getenv("HOSAKA_API_DOCS_URL_BASE", "/docs")


@dataclass
class _Index:
    commands: dict[str, str] = field(default_factory=dict)  # command_str -> feature_id
    feature_names: dict[str, str] = field(default_factory=dict)  # name -> feature_id


_index_cache: Optional[_Index] = None
_index_mtime: float = 0.0


def _load_index(path: Path = _CATALOG_PATH) -> _Index:
    global _index_cache, _index_mtime
    try:
        mtime = path.stat().st_mtime if path.exists() else 0.0
    except OSError:
        mtime = 0.0
    if _index_cache is not None and mtime == _index_mtime:
        return _index_cache
    idx = _Index()
    if not path.exists():
        _index_cache = idx
        _index_mtime = mtime
        return idx
    try:
        import yaml  # type: ignore
    except ImportError:
        _index_cache = idx
        _index_mtime = mtime
        return idx
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        _index_cache = idx
        _index_mtime = mtime
        return idx
    for f in data.get("features", []) or []:
        fid = f.get("id")
        if not fid:
            continue
        idx.feature_names[(f.get("name") or fid).lower()] = fid
        for cmd in f.get("commands") or []:
            idx.commands[cmd.strip().lower()] = fid
        if f.get("baller_command"):
            idx.commands[f["baller_command"].strip().lower()] = fid
    _index_cache = idx
    _index_mtime = mtime
    return idx


# ── public API ───────────────────────────────────────────────────────────────


@dataclass
class Suggestion:
    input: str
    did_you_mean: Optional[str] = None
    feature_id: Optional[str] = None
    manual_url: Optional[str] = None
    api_docs_url: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "did_you_mean": self.did_you_mean,
            "feature_id": self.feature_id,
            "manual_url": self.manual_url,
            "api_docs_url": self.api_docs_url,
            "message": self.message,
        }


def _manual_url(feature_id: Optional[str]) -> str:
    if not feature_id:
        return f"{_BASE_MANUAL_URL}/"
    return f"{_BASE_MANUAL_URL}/{feature_id}"


def _api_docs_url() -> str:
    return _BASE_API_DOCS_URL


def suggest_for(text: str, *, cutoff: float = 0.55, n: int = 3) -> Suggestion:
    """Given an unknown command/string, return the best guess + helpful URLs.

    Always returns a Suggestion (never None). On total miss, the message
    points at the manual index.
    """
    try:
        if not text:
            return Suggestion(
                input="",
                manual_url=_manual_url(None),
                api_docs_url=_api_docs_url(),
                message=f"try `/manual` to see everything ({_manual_url(None)})",
            )
        idx = _load_index()
        needle = text.strip().lower()

        # exact hit
        if needle in idx.commands:
            fid = idx.commands[needle]
            return Suggestion(
                input=text,
                did_you_mean=text.strip(),
                feature_id=fid,
                manual_url=_manual_url(fid),
                api_docs_url=_api_docs_url(),
                message=f"`{text.strip()}` is a known command — see {_manual_url(fid)}",
            )

        # fuzzy match against commands first, then feature names
        haystacks = list(idx.commands) + list(idx.feature_names)
        matches = difflib.get_close_matches(needle, haystacks, n=n, cutoff=cutoff)
        if matches:
            best = matches[0]
            fid = idx.commands.get(best) or idx.feature_names.get(best)
            return Suggestion(
                input=text,
                did_you_mean=best,
                feature_id=fid,
                manual_url=_manual_url(fid),
                api_docs_url=_api_docs_url(),
                message=(
                    f"unknown: `{text}`. did you mean `{best}`? "
                    f"see {_manual_url(fid)} or full api at {_api_docs_url()}"
                ),
            )

        return Suggestion(
            input=text,
            manual_url=_manual_url(None),
            api_docs_url=_api_docs_url(),
            message=(
                f"unknown: `{text}`. browse `/manual` ({_manual_url(None)}) "
                f"or the api docs ({_api_docs_url()})."
            ),
        )
    except Exception:
        return Suggestion(
            input=text,
            manual_url=_manual_url(None),
            api_docs_url=_api_docs_url(),
            message=f"see {_manual_url(None)} or {_api_docs_url()}",
        )


def known_commands() -> list[str]:
    return sorted(_load_index().commands)


def reset_cache() -> None:
    """For tests."""
    global _index_cache, _index_mtime
    _index_cache = None
    _index_mtime = 0.0


__all__ = ["Suggestion", "suggest_for", "known_commands", "reset_cache"]
