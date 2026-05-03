"""Secrets health checks: presence + format + live API probe."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from hosaka.secrets import spec, store

log = logging.getLogger("hosaka.secrets.check")

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"
STATUS_UNREACHABLE = "unreachable"
STATUS_SKIPPED = "skipped"


@dataclass
class CheckResult:
    name: str
    status: str
    source: str = ""
    detail: str = ""
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "source": self.source,
            "detail": self.detail,
            "required": self.required,
        }


def _resolve(name: str) -> tuple[str, str]:
    """Return (value, source) for a given env var, checking env -> JSON store."""
    raw = os.environ.get(name, "").strip()
    if raw:
        return raw, "env"
    raw = (store.get(name) or "").strip()
    if raw:
        return raw, "~/.hosaka/secrets.json"
    if name == "OPENAI_API_KEY":
        try:
            from hosaka.llm.openai_adapter import resolve_api_key
        except Exception:  # pragma: no cover - defensive
            return "", ""
        key, src = resolve_api_key()
        if key:
            return key, src or "fallback"
    return "", ""


def _probe_openai(key: str, *, timeout: float = 5.0) -> CheckResult:
    try:
        import httpx
    except ImportError:
        return CheckResult(
            name="OPENAI_API_KEY",
            status=STATUS_SKIPPED,
            detail="httpx not installed; skipping live probe",
        )
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
    url = f"{base}/v1/models"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        return CheckResult(
            name="OPENAI_API_KEY",
            status=STATUS_UNREACHABLE,
            detail=f"could not reach {base}: {exc}",
        )
    if resp.status_code == 200:
        return CheckResult(name="OPENAI_API_KEY", status=STATUS_OK, detail=f"{base} accepted the key")
    if resp.status_code in (401, 403):
        try:
            err = resp.json().get("error") or {}
        except Exception:  # noqa: BLE001
            err = {}
        message = err.get("message") or resp.text[:200]
        code = err.get("code") or err.get("type") or resp.status_code
        return CheckResult(
            name="OPENAI_API_KEY",
            status=STATUS_INVALID,
            detail=f"{base} rejected the key ({code}): {message}",
        )
    return CheckResult(
        name="OPENAI_API_KEY",
        status=STATUS_UNREACHABLE,
        detail=f"unexpected {resp.status_code} from {base}",
    )


def check_key(key: spec.Key, *, probe: bool = True, timeout: float = 5.0) -> CheckResult:
    value, source = _resolve(key.name)
    required = key in spec.REQUIRED
    if not value:
        if not required:
            return CheckResult(
                name=key.name,
                status=STATUS_OK if key.default else STATUS_MISSING,
                source=f"default={key.default}" if key.default else "",
                detail="optional; using default" if key.default else "optional; not set",
                required=False,
            )
        return CheckResult(
            name=key.name,
            status=STATUS_MISSING,
            detail=f"required for {key.purpose or 'Hosaka'}",
            required=True,
        )

    if key.validator:
        problem = key.validator(value)
        if problem:
            return CheckResult(
                name=key.name,
                status=STATUS_INVALID,
                source=source,
                detail=problem,
                required=required,
            )

    if probe and key.probe == "openai_chat_models":
        result = _probe_openai(value, timeout=timeout)
        result.source = source
        result.required = required
        return result

    return CheckResult(
        name=key.name,
        status=STATUS_OK,
        source=source,
        detail="present" + (" (validated)" if key.validator else ""),
        required=required,
    )


def run_checks(*, required_only: bool = False, probe: bool = True, timeout: float = 5.0) -> list[CheckResult]:
    keys: list[spec.Key] = list(spec.REQUIRED)
    if not required_only:
        keys.extend(spec.OPTIONAL)
    return [check_key(k, probe=probe, timeout=timeout) for k in keys]


def has_failures(results: list[CheckResult]) -> bool:
    bad = {STATUS_MISSING, STATUS_INVALID}
    return any(r.required and r.status in bad for r in results)
