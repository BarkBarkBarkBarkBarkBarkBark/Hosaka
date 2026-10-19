"""One guarded API for metadata-only views and approved trusted-local actions."""
from __future__ import annotations

import asyncio
import os
import threading
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, unquote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hosaka.extensions.manager import Manager, digest
from hosaka.extensions.manifest import ExtensionError, package_file, read_document, validate_id, validate_package
from hosaka.extensions.runner import InvocationError, cancel, run, _directory, _slots
from hosaka.extensions.worker import Context
from hosaka.web.api_v1 import require_write


def available(request: Request) -> None:
    if os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(403, "Extensions are disabled on public hosts.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site extension requests are forbidden.")
    target = urlsplit(str(request.url))
    loopback = {"127.0.0.1", "::1", "localhost"}
    local = request.client is not None and request.client.host in loopback
    if local and target.hostname not in loopback:
        raise HTTPException(403, "Use a loopback hostname for the local extension API.")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        local_dev = (
            parsed.hostname in loopback and target.hostname in loopback
            and local and parsed.port == 5173
        )
        if parsed.scheme not in {"http", "https"} or (
            (parsed.scheme, parsed.netloc) != (target.scheme, target.netloc) and not local_dev
        ):
            raise HTTPException(403, "Extension requests require the host's own origin.")


router = APIRouter(
    prefix="/api/v1/extensions", tags=["extensions"],
    dependencies=[Depends(require_write), Depends(available)],
)
_pending: dict[tuple[str, str], threading.Event] = {}
_pending_lock = threading.Lock()


def manager() -> Manager:
    return Manager()


def _id(identifier: str) -> str:
    try:
        return validate_id(identifier)
    except ExtensionError as exc:
        raise HTTPException(422, str(exc)) from exc


def _info(instance: Manager, identifier: str) -> dict:
    try:
        return instance.info(_id(identifier))
    except (OSError, ExtensionError, ValueError) as exc:
        raise HTTPException(409, "Extension is unavailable; run extensions doctor.") from exc


def file_context(instance: Manager, identifier: str, expected: str | None = None) -> Context:
    info = _info(instance, identifier)
    if not info["execution_available"] or "storage:directory" not in info["grants"]:
        raise HTTPException(403, "File access requires an approved enabled package and managed data grant.")
    package = validate_package(Path(info["path"]))
    if package.manifest.permissions.filesystem != "data-directory" or (expected and digest(package.root) != expected):
        raise HTTPException(409, "File capability or source digest changed.")
    root = instance.root / "extension-data" / identifier
    if root.is_symlink() or not root.resolve().is_relative_to(instance.root.resolve()):
        raise HTTPException(409, "Managed data directory is unsafe.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return Context(root, True, managed=True)


@router.post("/{identifier}/files", openapi_extra={"requestBody": {"required": True, "content": {
    "application/octet-stream": {"schema": {"type": "string", "format": "binary", "maxLength": 10485760}},
}}})
async def upload_file(
    identifier: str, request: Request, instance: Manager = Depends(manager),
    expected: str = Header(default="", alias="X-Extension-Digest"),
    original_name: str = Header(default="", alias="X-Extension-Filename"),
) -> dict:
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise HTTPException(422, "Use the current source digest.")
    context = file_context(instance, identifier, expected)
    name = unquote(original_name)
    if not name or len(name) > 255 or Path(name).name != name or "\\" in name or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "Use a plain original filename.")
    token = uuid4().hex
    target = Path(context.data_path("uploads/" + token))
    if len(list(target.parent.iterdir())) >= 128:
        raise HTTPException(409, "Unattached upload limit reached; import or explicitly remove staged files.")
    fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
    total = 0
    try:
        async def consume(stream):
            nonlocal total
            async for chunk in request.stream():
                total += len(chunk)
                if total > 10485760:
                    raise HTTPException(413, "Evidence uploads are limited to 10 MiB.")
                stream.write(chunk)
        with os.fdopen(fd, "wb") as stream, _slots(_directory(instance, "state/extension-jobs"), identifier):
            await asyncio.wait_for(consume(stream), timeout=30)
            stream.flush()
            os.fsync(stream.fileno())
        if total == 0:
            raise HTTPException(422, "Empty uploads are not accepted.")
        file_context(instance, identifier, expected)
        os.replace(temporary, target)
    except asyncio.TimeoutError:
        raise HTTPException(408, "Upload exceeded its 30-second time limit.") from None
    except InvocationError as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"id": token, "filename": name, "size_bytes": total}


@router.get("/{identifier}/files/{name}")
def download_file(identifier: str, name: str, instance: Manager = Depends(manager)) -> FileResponse:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", name):
        raise HTTPException(422, "Invalid object name.")
    context = file_context(instance, identifier)
    try:
        path = Path(context.data_path("files/" + name))
    except (PermissionError, ValueError):
        raise HTTPException(403, "Object path is unsafe.") from None
    if not path.is_file():
        raise HTTPException(404, "Object not available locally; check attachment synchronization.")
    return FileResponse(path, media_type="application/octet-stream", filename=name,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.get("")
def catalog(instance: Manager = Depends(manager)) -> dict:
    try:
        report = instance.discover()
    except (OSError, ExtensionError, ValueError) as exc:
        raise HTTPException(503, "Extension metadata is invalid or unreadable; run extensions doctor.") from exc
    return {
        "extensions": [
            {key: item[key] for key in ("id", "name", "version", "menu", "execution_available", "execution_reason")}
            for item in sorted(report["extensions"], key=lambda item: (item["menu"]["order"], item["id"]))
            if item["registered"] and item["enabled"]
        ],
        "invalid_package_count": len(report["errors"]), "safe_mode": report["safe_mode"],
        "execution_mode": "trusted-local", "sandboxed": False,
    }


@router.get("/{identifier}/view")
def view(identifier: str, instance: Manager = Depends(manager)) -> dict:
    info = _info(instance, identifier)
    if not info["registered"] or not info["enabled"]:
        raise HTTPException(409, "Extension is disabled or unregistered.")
    try:
        package = validate_package(Path(info["path"]))
        actions = {}
        for name, action in package.manifest.actions.items():
            schema = read_document(package_file(package.root, action.input_schema), json_only=True)
            properties = schema.get("properties")
            actions[name] = {
                "description": action.description,
                "input_keys": list(properties) if isinstance(properties, dict) else None,
            }
        source_digest = digest(package.root)
    except (OSError, ExtensionError) as exc:
        raise HTTPException(409, "Package source changed or became unavailable; reopen the view.") from exc
    return {
        "id": identifier, "name": info["name"], "version": info["version"],
        "view": package.view, "actions": actions, "digest": source_digest,
        "execution_available": info["execution_available"],
        "execution_reason": info["execution_reason"],
        "execution_mode": "trusted-local", "sandboxed": False,
    }


class InvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invocation_id: UUID
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    params: dict[str, Any] = Field(max_length=32)


async def invocation_body(request: Request) -> InvocationRequest:
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > 32768):
        raise HTTPException(413, "Extension request exceeds 32 KiB.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 32768:
            raise HTTPException(413, "Extension request exceeds 32 KiB.")
    try:
        return InvocationRequest.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, "Invalid extension request; use an invocation UUID, source digest and JSON params.") from exc


@router.post(
    "/{identifier}/actions/{action}",
    openapi_extra={"requestBody": {"required": True, "content": {
        "application/json": {"schema": InvocationRequest.model_json_schema()},
    }}},
)
async def invoke(
    request: Request, identifier: str, action: str,
    body: InvocationRequest = Depends(invocation_body), instance: Manager = Depends(manager),
) -> JSONResponse:
    _id(identifier)
    _id(action)
    cancellation = threading.Event()
    key = (identifier, str(body.invocation_id))
    with _pending_lock:
        if key in _pending or len(_pending) >= 2:
            raise HTTPException(409, "The extension API already has two active requests.")
        _pending[key] = cancellation
    task = asyncio.create_task(asyncio.to_thread(
        run, instance, identifier, action, body.params,
        invocation_id=str(body.invocation_id), cancellation=cancellation, expected_digest=body.digest,
    ))
    try:
        while not task.done():
            await asyncio.sleep(0.05)
            if await request.is_disconnected():
                cancellation.set()
        report = await task
        code = report["error"]["code"] if report["error"] else ""
        status = {
            "not_authorized": 403, "invalid_input": 422, "unknown_action": 404,
            "busy": 409, "stale_view": 409, "source_changed": 409, "cancelled": 409,
            "timeout": 504, "invalid_output": 502, "invalid_protocol": 502,
            "process_failed": 502, "extension_exception": 502, "output_limit": 502,
            "invocation_failed": 503, "logging_failed": 503,
        }.get(code, 200)
        return JSONResponse(report, status_code=status)
    finally:
        cancellation.set()
        with _pending_lock:
            _pending.pop(key, None)


@router.post("/{identifier}/cancel/{invocation_id}")
def cancel_invocation(identifier: str, invocation_id: UUID, instance: Manager = Depends(manager)) -> dict:
    _id(identifier)
    with _pending_lock:
        cancellation = _pending.get((identifier, str(invocation_id)))
        if cancellation is not None:
            cancellation.set()
            return {"cancel_requested": True, "invocation_id": str(invocation_id)}
    try:
        cancel(instance, _id(identifier), str(invocation_id))
    except (InvocationError, OSError, ValueError) as exc:
        raise HTTPException(409, "Invocation is no longer active or cannot be cancelled.") from exc
    return {"cancel_requested": True, "invocation_id": str(invocation_id)}
