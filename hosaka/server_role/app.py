"""Hardware-free HTTP boundary for Jetson inference."""
from __future__ import annotations

import inspect
import os
import uuid
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response

from hosaka.protocol.audio import InvalidAudio, MEDIA_TYPE, validate_wav

Responder = Callable[[bytes, str], bytes | None | Awaitable[bytes | None]]


def create_app(responder: Responder | None = None) -> FastAPI:
    app = FastAPI(title="Hosaka Jetson Inference", version="1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok" if responder else "unavailable", "role": "server"}

    @app.post("/respond")
    async def respond(request: Request) -> Response:
        request_id = uuid.uuid4().hex
        response_headers = {"X-Hosaka-Request-ID": request_id}
        expected_token = os.getenv("HOSAKA_INFERENCE_TOKEN", "").strip()
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
        result = responder(audio, request.headers.get("x-session-id", "hosaka-pi"))
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            return Response(status_code=204, headers={**response_headers, "X-Hosaka-Decision": "remain_silent"})
        try:
            validate_wav(result)
        except InvalidAudio as exc:
            raise HTTPException(503, f"inference responder returned invalid WAV: {exc}") from exc
        return Response(result, media_type=MEDIA_TYPE, headers={**response_headers, "X-Hosaka-Decision": "speak"})

    return app


app = create_app()