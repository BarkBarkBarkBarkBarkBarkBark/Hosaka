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

import logging
import os
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from hosaka.web.api_v1 import require_auth, require_write
from hosaka.voice import tools as voice_tools

log = logging.getLogger("hosaka.web.voice")

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


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


# ── ephemeral token ──────────────────────────────────────────────────────


@router.post(
    "/ephemeral-token",
    response_model=EphemeralOut,
    summary="Mint a short-lived OpenAI Realtime session token for the browser",
    dependencies=[Depends(require_auth)],
)
async def voice_ephemeral_token() -> EphemeralOut:
    """Delegate to OpenAI's ``POST /v1/realtime/sessions`` endpoint.

    The real ``OPENAI_API_KEY`` stays on this process — the browser
    only ever sees ``client_secret.value`` (valid for ~1 minute).
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "OPENAI_API_KEY is not set on this appliance")

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
        log.warning("ephemeral token mint failed: %s", exc)
        raise HTTPException(502, f"upstream error: {exc}") from exc

    return EphemeralOut(
        client_secret=dict(data.get("client_secret") or {}),
        session=data,
        tools=voice_tools.TOOL_SCHEMAS,
        instructions=voice_tools.SYSTEM_INSTRUCTIONS,
        voice=str(data.get("voice") or DEFAULT_VOICE),
        model=str(data.get("model") or DEFAULT_MODEL),
    )


# ── tool dispatch bridge (browser path) ─────────────────────────────────-


@router.post(
    "/tools/{name}",
    response_model=ToolOut,
    summary="Run a voice tool server-side (called by the browser on function_call events)",
    dependencies=[Depends(require_write)],
)
def voice_tool_dispatch(name: str, body: ToolIn = Body(default_factory=ToolIn)) -> ToolOut:
    if name not in {t["name"] for t in voice_tools.TOOL_SCHEMAS}:
        raise HTTPException(404, f"unknown tool: {name}")
    output = voice_tools.dispatch(name, body.args)
    return ToolOut(ok=True, output=output)


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
