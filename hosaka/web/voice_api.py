"""`/api/v1/voice/*` — voice-mode HTTP surface.

Three jobs:

1. ``POST /ephemeral-token`` — mint a short-lived Realtime session token
   so the browser can open a WebRTC peer connection without ever
   holding the real ``OPENAI_API_KEY``.
2. ``POST /tools/{name}`` — run a tool the browser received as a
   ``function_call`` event. Uses the same dispatcher as the headless
   daemon so both paths behave identically.
3. ``GET /camera/snapshot.jpg`` — one JPEG from the USB webcam for the
   VoicePanel preview and for the Python ``see()`` tool's fallback.

The router reuses the ``require_auth`` / ``require_write`` dependencies
from :mod:`hosaka.web.api_v1` so voice shares the same auth story as
the rest of the v1 surface.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from urllib.parse import urlparse
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from hosaka.llm.openai_adapter import resolve_api_key
from hosaka.web.api_v1 import _is_loopback, _load_token, require_auth
from hosaka.voice import tools as voice_tools

log = logging.getLogger("hosaka.web.voice")

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])
_bearer = HTTPBearer(auto_error=False)
_VOICE_JOB_TTL_SECONDS = 15 * 60
_voice_jobs: dict[str, dict[str, Any]] = {}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


PUBLIC_MODE = _env_flag("HOSAKA_PUBLIC_MODE", False)


def _is_same_origin_browser(req) -> bool:
    host = (req.headers.get("host") or "").split(":", 1)[0].strip().lower()
    if not host:
        return False
    for key in ("origin", "referer"):
        raw = (req.headers.get(key) or "").strip()
        if not raw:
            continue
        try:
            parsed = urlparse(raw)
        except ValueError:
            continue
        if (parsed.hostname or "").strip().lower() == host:
            return True
    return False


def require_voice_write(
    req: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Allow writes from the hosted SPA even when Docker hides loopback.

    In local dev the browser talks to the container through a bridge IP, so
    the client no longer looks like 127.0.0.1. Same-origin requests from the
    Hosaka UI should still be treated as trusted local control-surface writes.
    """
    if _is_loopback(req) or _is_same_origin_browser(req):
        return
    expected = _load_token()
    if not expected:
        raise HTTPException(403, "no API token configured on this Pi")
    if creds and creds.scheme.lower() == "bearer" and creds.credentials == expected:
        return
    raise HTTPException(401, "missing or invalid bearer token")


def require_local_voice_agent() -> None:
    if PUBLIC_MODE:
        raise HTTPException(403, "local voice agent is disabled in public mode")


# ── models ───────────────────────────────────────────────────────────────


class EphemeralOut(BaseModel):
    """Subset of OpenAI's response, plus the tool schema echoed back.

    Browser code only needs ``client_secret.value`` to open the WebRTC
    peer connection; the rest is returned so the panel can show session
    metadata in its debug drawer without a second round-trip.
    """

    client_secret: dict[str, Any]
    session: dict[str, Any]
    tools: list[dict[str, Any]]
    instructions: str
    voice: str
    model: str
    api_shape: str = "ga"
    sdp_url: str = "https://api.openai.com/v1/realtime/calls"


class ToolIn(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class ToolOut(BaseModel):
    ok: bool
    output: str


class VoiceTodoOut(BaseModel):
    id: str
    at: int
    text: str
    source: str = "voice"


class VoiceTodosOut(BaseModel):
    todos: list[VoiceTodoOut]


class AgentTurnOut(BaseModel):
    ok: bool
    operator_text: str
    spoken_text: str
    internal_note: str = ""
    used_backend: str = "picoclaw"
    transcript_visibility: str = "operator+status"


class AgentJobCreateOut(BaseModel):
    ok: bool
    job_id: str
    status: str
    spoken_text: str = ""
    internal_note: str = ""
    used_backend: str = "picoclaw"


class AgentJobOut(BaseModel):
    ok: bool
    job_id: str
    status: str
    operator_text: str = ""
    spoken_text: str = ""
    internal_note: str = ""
    used_backend: str = "picoclaw"
    error: str = ""
    done: bool = False


# ── ephemeral token ──────────────────────────────────────────────────────


@router.post(
    "/ephemeral-token",
    response_model=EphemeralOut,
    summary="Mint a short-lived OpenAI Realtime session token for the browser",
    dependencies=[Depends(require_auth)],
)
@router.get(
    "/ephemeral-token",
    response_model=EphemeralOut,
    summary="Mint a short-lived OpenAI Realtime session token for the browser (GET alias)",
    dependencies=[Depends(require_auth)],
    include_in_schema=False,
)
async def voice_ephemeral_token() -> EphemeralOut:
    """Delegate to OpenAI's ``POST /v1/realtime/sessions`` endpoint.

    The real ``OPENAI_API_KEY`` stays on this process — the browser
    only ever sees ``client_secret.value`` (valid for ~1 minute).
    """
    api_key, key_source = resolve_api_key()
    if not api_key:
        raise HTTPException(
            503,
            "OPENAI_API_KEY is not set on this appliance "
            "(checked env, llm.json, ~/.picoclaw/config.json)",
        )

    from hosaka.voice.realtime_client import (
        DEFAULT_MODEL,
        DEFAULT_VOICE,
        mint_ephemeral_session,
    )

    try:
        data = await mint_ephemeral_session(
            api_key,
            tools=voice_tools.TOOL_SCHEMAS,
            instructions=voice_tools.SYSTEM_INSTRUCTIONS,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("ephemeral token mint failed via %s: %s", key_source or "unknown", exc)
        raise HTTPException(502, f"upstream error: {exc}") from exc

    session_data = data.get("session") if isinstance(data.get("session"), dict) else data
    client_secret = data.get("client_secret") if isinstance(data.get("client_secret"), dict) else {}
    if not client_secret and data.get("value"):
        client_secret = {
            "value": data.get("value"),
            "expires_at": data.get("expires_at"),
        }
    audio = session_data.get("audio") if isinstance(session_data, dict) else {}
    audio_output = audio.get("output") if isinstance(audio, dict) else {}

    return EphemeralOut(
        client_secret=dict(client_secret or {}),
        session=session_data if isinstance(session_data, dict) else data,
        tools=voice_tools.TOOL_SCHEMAS,
        instructions=voice_tools.SYSTEM_INSTRUCTIONS,
        voice=str(data.get("voice") or audio_output.get("voice") or DEFAULT_VOICE),
        model=str(data.get("model") or session_data.get("model") or DEFAULT_MODEL),
        api_shape=str(data.get("_hosaka_api_shape") or "ga"),
        sdp_url=str(data.get("_hosaka_sdp_url") or "https://api.openai.com/v1/realtime/calls"),
    )


# ── tool dispatch bridge (browser path) ─────────────────────────────────-


@router.post(
    "/tools/{name}",
    response_model=ToolOut,
    summary="Run a voice tool server-side (called by the browser on function_call events)",
    dependencies=[Depends(require_voice_write)],
)
def voice_tool_dispatch(name: str, body: ToolIn = Body(default_factory=ToolIn)) -> ToolOut:
    if name not in {t["name"] for t in voice_tools.TOOL_SCHEMAS}:
        raise HTTPException(404, f"unknown tool: {name}")
    output = voice_tools.dispatch(name, body.args)
    return ToolOut(ok=True, output=output)


def _cleanup_voice_jobs() -> None:
    cutoff = time.time() - _VOICE_JOB_TTL_SECONDS
    stale = [job_id for job_id, job in _voice_jobs.items() if float(job.get("updated_at", 0)) < cutoff]
    for job_id in stale:
        _voice_jobs.pop(job_id, None)


def _job_snapshot(job_id: str) -> dict[str, Any]:
    job = _voice_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "voice job not found")
    return {
        "ok": True,
        "job_id": job_id,
        "status": str(job.get("status") or "queued"),
        "operator_text": str(job.get("operator_text") or ""),
        "spoken_text": str(job.get("spoken_text") or ""),
        "internal_note": str(job.get("internal_note") or ""),
        "used_backend": str(job.get("used_backend") or "picoclaw"),
        "error": str(job.get("error") or ""),
        "done": bool(job.get("done", False)),
    }


def _update_job(job_id: str, **changes: Any) -> None:
    job = _voice_jobs.get(job_id)
    if not job:
        return
    job.update(changes)
    job["updated_at"] = time.time()


async def _run_agent_turn(content: bytes, *, filename: str, content_type: str) -> dict[str, Any]:
    transcript = await voice_tools_transcribe_upload(
        content,
        filename=filename,
        content_type=content_type,
    )

    if not transcript.strip():
        return {
            "operator_text": "",
            "spoken_text": "i didn't catch that.",
            "internal_note": "empty transcription",
            "used_backend": "picoclaw",
        }

    result = await asyncio.to_thread(voice_tools.run_agent_voice_turn, transcript)
    return {
        "operator_text": str(result.get("operator_text") or transcript),
        "spoken_text": str(result.get("spoken") or ""),
        "internal_note": str(result.get("thought") or ""),
        "used_backend": "picoclaw",
    }


async def _process_agent_job(
    job_id: str,
    content: bytes,
    *,
    filename: str,
    content_type: str,
) -> None:
    try:
        _update_job(job_id, status="transcribing", internal_note="whisper is transcribing")
        transcript = await voice_tools_transcribe_upload(
            content,
            filename=filename,
            content_type=content_type,
        )

        if not transcript.strip():
            _update_job(
                job_id,
                status="completed",
                operator_text="",
                spoken_text="i didn't catch that.",
                internal_note="empty transcription",
                done=True,
            )
            return

        _update_job(
            job_id,
            status="thinking",
            operator_text=transcript,
            internal_note="picoclaw is working",
        )
        result = await asyncio.to_thread(voice_tools.run_agent_voice_turn, transcript)
        _update_job(
            job_id,
            status="completed",
            operator_text=str(result.get("operator_text") or transcript),
            spoken_text=str(result.get("spoken") or ""),
            internal_note=str(result.get("thought") or ""),
            used_backend="picoclaw",
            done=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("voice agent job failed: %s", exc)
        _update_job(
            job_id,
            status="error",
            error=str(exc),
            spoken_text="i hit a problem while working that voice request.",
            internal_note="agent turn failed",
            done=True,
        )


@router.post(
    "/agent-turn",
    response_model=AgentTurnOut,
    summary="Transcribe uploaded speech and route the turn through PicoClaw",
    dependencies=[Depends(require_voice_write), Depends(require_local_voice_agent)],
)
async def voice_agent_turn(audio: UploadFile = File(...)) -> AgentTurnOut:
    content = await audio.read()
    if not content:
        raise HTTPException(400, "empty audio upload")

    try:
        result = await _run_agent_turn(
            content,
            filename=audio.filename or "voice.webm",
            content_type=audio.content_type or "application/octet-stream",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("voice agent transcription failed: %s", exc)
        raise HTTPException(502, f"transcription failed: {exc}") from exc

    return AgentTurnOut(
        ok=True,
        operator_text=str(result.get("operator_text") or ""),
        spoken_text=str(result.get("spoken_text") or ""),
        internal_note=str(result.get("internal_note") or ""),
        used_backend=str(result.get("used_backend") or "picoclaw"),
    )


@router.post(
    "/agent-jobs",
    response_model=AgentJobCreateOut,
    summary="Queue a local voice-agent turn and return immediately with a job id",
    dependencies=[Depends(require_voice_write), Depends(require_local_voice_agent)],
)
async def voice_agent_job_create(audio: UploadFile = File(...)) -> AgentJobCreateOut:
    content = await audio.read()
    if not content:
        raise HTTPException(400, "empty audio upload")

    _cleanup_voice_jobs()
    job_id = uuid.uuid4().hex
    _voice_jobs[job_id] = {
        "status": "queued",
        "operator_text": "",
        "spoken_text": "heard you. working on it.",
        "internal_note": "turn queued",
        "used_backend": "picoclaw",
        "error": "",
        "done": False,
        "updated_at": time.time(),
    }
    asyncio.create_task(
        _process_agent_job(
            job_id,
            content,
            filename=audio.filename or "voice.webm",
            content_type=audio.content_type or "application/octet-stream",
        )
    )
    snapshot = _job_snapshot(job_id)
    return AgentJobCreateOut(
        ok=True,
        job_id=job_id,
        status=str(snapshot.get("status") or "queued"),
        spoken_text=str(snapshot.get("spoken_text") or ""),
        internal_note=str(snapshot.get("internal_note") or ""),
        used_backend=str(snapshot.get("used_backend") or "picoclaw"),
    )


@router.get(
    "/agent-jobs/{job_id}",
    response_model=AgentJobOut,
    summary="Read the current state of a queued local voice-agent turn",
    dependencies=[Depends(require_voice_write), Depends(require_local_voice_agent)],
)
async def voice_agent_job_get(job_id: str) -> AgentJobOut:
    _cleanup_voice_jobs()
    return AgentJobOut(**_job_snapshot(job_id))


# ── voice-added todo feed ────────────────────────────────────────────────


@router.get(
    "/todos",
    response_model=VoiceTodosOut,
    summary="Last N voice-added todos (for the VoicePanel to mirror into the Todo list)",
    dependencies=[Depends(require_auth)],
)
def voice_todos(limit: int = 50) -> VoiceTodosOut:
    rows = voice_tools.read_voice_todos(limit=limit)
    out = [
        VoiceTodoOut(
            id=str(r.get("id", "")),
            at=int(r.get("at", 0)),
            text=str(r.get("text", "")),
            source=str(r.get("source", "voice")),
        )
        for r in rows
        if r.get("text")
    ]
    return VoiceTodosOut(todos=out)


# ── camera snapshot ──────────────────────────────────────────────────────


@router.get(
    "/camera/snapshot.jpg",
    summary="Single JPEG from the attached USB webcam",
    responses={200: {"content": {"image/jpeg": {}}}},
    response_class=Response,
    dependencies=[Depends(require_auth)],
)
def voice_camera_snapshot() -> Response:
    try:
        from hosaka.voice import camera
    except ImportError as exc:
        raise HTTPException(503, f"voice deps missing: {exc}") from exc
    try:
        jpeg = camera.snapshot_jpeg()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"camera unavailable: {exc}") from exc
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


async def voice_tools_transcribe_upload(
    content: bytes,
    *,
    filename: str,
    content_type: str,
) -> str:
    return await resolve_transcription(content, filename=filename, content_type=content_type)


async def resolve_transcription(
    content: bytes,
    *,
    filename: str,
    content_type: str,
) -> str:
    from hosaka.llm.openai_adapter import transcribe_audio_bytes
    import httpx

    # Retry on 429 (Whisper rate limit) with exponential backoff.
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            return await transcribe_audio_bytes(
                content,
                filename=filename,
                content_type=content_type,
                prompt=(
                    "Transcribe operator speech for a coding and device-control assistant. "
                    "Preserve filenames, shell terms, and short commands accurately."
                ),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < max_attempts - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                log.warning("Whisper 429 rate-limit — retrying in %ds (attempt %d/%d)", wait, attempt + 1, max_attempts)
                await asyncio.sleep(wait)
                continue
            raise
