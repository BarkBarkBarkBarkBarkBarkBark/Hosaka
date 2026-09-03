"""Hardware-free HTTP boundary for Jetson inference."""
from __future__ import annotations

import inspect
import os
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response

from hosaka.protocol.audio import InvalidAudio, MEDIA_TYPE, validate_wav
from hosaka.server_role.responder import OfflineResponder, ProviderError

Responder = Callable[[bytes, str], bytes | None | Awaitable[bytes | None]]


def _inference_token() -> str:
    token = os.getenv("HOSAKA_INFERENCE_TOKEN", "").strip()
    if token:
        return token
    path = Path(os.getenv("HOSAKA_INFERENCE_TOKEN_FILE", "/etc/hosaka/inference-token"))
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def create_app(responder: Responder | None = None) -> FastAPI:
    app = FastAPI(title="Hosaka Jetson Inference", version="1")

    @app.get("/health")
    async def health() -> dict[str, object]:
        missing = responder.missing_artifacts() if isinstance(responder, OfflineResponder) else []
        return {
            "status": "ok" if responder and not missing else "unavailable",
            "role": "server",
            "missing_artifacts": missing,
        }

    @app.get("/status")
    async def status() -> dict[str, object]:
        if not isinstance(responder, OfflineResponder):
            return {"status": "unavailable", "role": "server"}
        return {
            "status": "ok" if not responder.missing_artifacts() else "unavailable",
            "role": "server",
            "whisper_model": str(responder.whisper_model),
            "whisper_gpu": responder.whisper_gpu,
            "vad_model": str(responder.vad_model),
            "ollama_url": responder.ollama_url,
            "ollama_model": responder.ollama_model,
            "piper_model": str(responder.piper_model),
            "missing_artifacts": responder.missing_artifacts(),
        }

    @app.post("/respond")
    async def respond(request: Request) -> Response:
        request_id = uuid.uuid4().hex
        response_headers = {"X-Hosaka-Request-ID": request_id}
        expected_token = _inference_token()
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1"}:
            if not expected_token:
                raise HTTPException(403, "HOSAKA_INFERENCE_TOKEN is not configured")
            if request.headers.get("authorization") != f"Bearer {expected_token}":
                raise HTTPException(401, "missing or invalid bearer token")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != MEDIA_TYPE:
            raise HTTPException(415, f"expected {MEDIA_TYPE}")
        audio = await request.body()
        try:
            validate_wav(audio, max_seconds=float(os.getenv("HOSAKA_MAX_AUDIO_SECONDS", "30")))
        except InvalidAudio as exc:
            raise HTTPException(
                400,
                {"code": "invalid_audio", "message": str(exc), "expected": "16000 Hz mono pcm_s16le", "request_id": request_id},
                headers=response_headers,
            ) from exc
        if responder is None:
            raise HTTPException(503, "Jetson inference providers are not provisioned", headers=response_headers)
        try:
            result = responder(audio, request.headers.get("x-session-id", "hosaka-pi"))
            if inspect.isawaitable(result):
                result = await result
        except ProviderError as exc:
            raise HTTPException(503, str(exc), headers=response_headers) from exc
        if result is None:
            return Response(status_code=204, headers={**response_headers, "X-Hosaka-Decision": "remain_silent"})
        try:
            validate_wav(result)
        except InvalidAudio as exc:
            raise HTTPException(503, f"inference responder returned invalid WAV: {exc}") from exc
        return Response(result, media_type=MEDIA_TYPE, headers={**response_headers, "X-Hosaka-Decision": "speak"})

    return app


app = create_app(OfflineResponder.from_env())