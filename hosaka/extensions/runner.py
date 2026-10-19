"""Bounded trusted-local invocation. This is explicitly NOT an OS sandbox."""
from __future__ import annotations

import fcntl
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, TYPE_CHECKING

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from referencing.exceptions import Unresolvable

from hosaka.extensions.manifest import ExtensionError, Package, package_file, read_document, validate_id, validate_package

if TYPE_CHECKING:
    from hosaka.extensions.manager import Manager, Registration

MAX_REQUEST_BYTES = 16384
WORKER = Path(__file__).with_name("worker.py")


class InvocationError(ExtensionError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def approval_reason(package: Package, registration: Registration | None, *, safe_mode: bool = False) -> str | None:
    from hosaka.extensions.manager import digest

    if os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}:
        return "Extension execution is disabled on public hosts."
    if os.geteuid() == 0:
        return "Trusted-local execution refuses root; run Hosaka as the unprivileged operator."
    if safe_mode or os.getenv("HOSAKA_EXTENSIONS_SAFE_MODE", "").lower() in {"1", "true", "yes", "on"}:
        return "Extension safe mode is enabled."
    if registration is None or registration.removed or not registration.enabled:
        return "Extension is disabled or unregistered."
    if registration.execution_mode != "trusted-local" or not registration.approved_digest:
        return "Owner approval is required: extensions trust ID --trusted-local."
    if digest(package.root) != registration.approved_digest:
        return "Package source changed; inspect it and explicitly approve its new digest."
    if package.manifest.permissions.filesystem == "data-only" and "storage:self" not in registration.grants:
        return "storage:self has not been granted; trust with --allow-storage after inspection."
    if package.manifest.permissions.filesystem == "data-directory" and (
        "storage:directory" not in registration.grants or "storage:self" not in registration.grants
    ):
        return "Managed storage requires --allow-storage and --allow-managed-data after inspection."
    return None


def _directory(manager: Manager, relative: str) -> Path:
    target = manager.root / relative
    if not target.resolve().is_relative_to(manager.root.resolve()) or target.is_symlink():
        raise InvocationError("unsafe_path", "Runtime data/log/state path escapes the Hosaka data root.")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    return target


@contextmanager
def _slots(state: Path, identifier: str, background: bool = False) -> Generator[None, None, None]:
    handles = []
    try:
        names = (f"{identifier}.background.lock", "background-host.lock") if background else (f"{identifier}.lock",)
        for name in names:
            path = state / name
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            handle = os.fdopen(fd, "a")
            handles.append(handle)
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InvocationError("busy", "This extension already has an active invocation.") from exc
        for index in range(2):
            fd = os.open(state / f"slot-{index}.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            handle = os.fdopen(fd, "a")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
            else:
                handles.append(handle)
                break
        else:
            raise InvocationError("busy", "The two-invocation host limit is reached.")
        yield
    finally:
        for handle in reversed(handles):
            handle.close()


def _validate_instance(instance: object, schema: dict, kind: str) -> None:
    try:
        Draft202012Validator(schema).validate(instance)
    except (SchemaValidationError, Unresolvable, RecursionError) as exc:
        raise InvocationError(f"invalid_{kind}", f"Extension {kind} does not satisfy its declared schema.") from exc


def _response_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field")
        result[key] = value
    return result


def cancel(manager: Manager, identifier: str, invocation: str) -> None:
    validate_id(identifier)
    invocation = str(uuid.UUID(invocation))
    state = _directory(manager, "state/extension-jobs")
    active = state / f"{identifier}.{invocation}.active"
    if not active.is_file():
        raise InvocationError("not_running", "That invocation is no longer active.")
    path = state / f"{identifier}.{invocation}.cancel"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)


def _still_allowed(manager: Manager, identifier: str, approved_digest: str, storage: bool,
                   managed: bool = False, network: bool = False, background: bool = False) -> None:
    registry = manager.registry()
    entry = registry.extensions.get(identifier)
    if (
        registry.safe_mode or os.getenv("HOSAKA_EXTENSIONS_SAFE_MODE", "").lower() in {"1", "true", "yes", "on"}
        or os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}
        or entry is None or not entry.enabled or entry.removed
        or entry.approved_digest != approved_digest or entry.execution_mode != "trusted-local"
        or (storage and "storage:self" not in entry.grants)
        or (managed and "storage:directory" not in entry.grants)
        or (network and "network:self" not in entry.grants)
        or (background and "background:self" not in entry.grants)
    ):
        raise InvocationError("cancelled", "Invocation cancelled by disable, removal, approval/grant revocation or safe mode.")


def _process(request: dict, package: Package, manager: Manager, marker: Path, cancellation: threading.Event | None) -> dict:
    wire = json.dumps(request, allow_nan=False).encode("utf-8")
    if len(wire) > 32768:
        raise InvocationError("invalid_input", "Invocation request exceeds 32 KiB.")
    if (cancellation is not None and cancellation.is_set()) or marker.exists():
        raise InvocationError("cancelled", "Invocation cancelled by its caller.")
    capabilities = {name: request.get(name, False) for name in ("managed", "network", "background")}
    _still_allowed(manager, request["extension_id"], request["approved_digest"], request["storage"], **capabilities)
    with tempfile.TemporaryDirectory(prefix="hosaka-extension-home-") as home:
        environment = {
            "HOME": home, "TMPDIR": home, "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8",
        }
        proc = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", str(WORKER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=request["package"], env=environment, start_new_session=True,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        output = bytearray()
        total = 0
        written = 0
        deadline = time.monotonic() + package.manifest.limits.timeout_seconds
        try:
            with selectors.DefaultSelector() as selector:
                for stream, direction, events in (
                    (proc.stdin, "input", selectors.EVENT_WRITE),
                    (proc.stdout, "output", selectors.EVENT_READ),
                    (proc.stderr, "diagnostics", selectors.EVENT_READ),
                ):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, events, direction)
                while selector.get_map():
                    if time.monotonic() > deadline:
                        raise InvocationError("timeout", "Extension exceeded its wall-time limit.")
                    if (cancellation is not None and cancellation.is_set()) or marker.exists():
                        raise InvocationError("cancelled", "Invocation cancelled by its caller.")
                    _still_allowed(manager, request["extension_id"], request["approved_digest"], request["storage"], **capabilities)
                    if proc.poll() is not None:
                        _kill_group(proc)
                    for key, _ in selector.select(0.05):
                        if key.data == "input":
                            try:
                                count = os.write(key.fd, wire[written:written + 4096])
                            except BrokenPipeError:
                                count = 0
                                written = len(wire)
                            written += count
                            if written >= len(wire):
                                selector.unregister(key.fd)
                                proc.stdin.close()
                            continue
                        chunk = os.read(key.fd, 4096)
                        if not chunk:
                            selector.unregister(key.fd)
                            continue
                        total += len(chunk)
                        if total > package.manifest.limits.max_output_bytes:
                            raise InvocationError("output_limit", "Extension stdout/stderr exceeded the declared combined limit.")
                        if key.data == "output":
                            output.extend(chunk)
            return_code = proc.wait(timeout=1)
            if return_code != 0:
                raise InvocationError("process_failed", "Extension process exited unsuccessfully; its output is not trusted.")
            try:
                response = json.loads(output, object_pairs_hook=_response_object)
                json.dumps(response, allow_nan=False, ensure_ascii=False).encode("utf-8")
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise InvocationError("invalid_protocol", "Extension did not return one valid JSON response.") from exc
            if (
                not isinstance(response, dict) or set(response) != {"protocol_version", "invocation_id", "result", "error", "events"}
                or type(response["protocol_version"]) is not int or response["protocol_version"] != 1
                or response["invocation_id"] != request["invocation_id"]
                or not isinstance(response["events"], list) or len(response["events"]) > 32
            ):
                raise InvocationError("invalid_protocol", "Extension response protocol or invocation identity is invalid.")
            for event in response["events"]:
                if (
                    not isinstance(event, dict) or set(event) != {"event", "metadata_fields"}
                    or not isinstance(event["event"], str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", event["event"])
                    or not isinstance(event["metadata_fields"], list) or len(event["metadata_fields"]) > 8
                    or any(not isinstance(field, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", field) for field in event["metadata_fields"])
                ):
                    raise InvocationError("invalid_protocol", "Extension event metadata is invalid.")
            return response
        finally:
            _kill_group(proc)
            proc.wait(timeout=2)
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _record(manager: Manager, identifier: str, report: dict, events: list) -> None:
    directory = _directory(manager, "logs/extensions")
    path = directory / f"{identifier}.jsonl"
    previous = path.with_suffix(".previous.jsonl")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "invocation_id": report["invocation_id"], "extension_id": identifier,
        "action": report["action"], "ok": report["ok"], "duration_ms": report["duration_ms"],
        "error_code": report["error"]["code"] if report["error"] else None,
        "execution_mode": "trusted-local", "event_count": len(events),
        "events": events,
    }
    lock_fd = os.open(directory / f"{identifier}.log.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_symlink() or previous.is_symlink():
            raise InvocationError("unsafe_log", "Extension log must not be a symlink.")
        line = json.dumps(record, ensure_ascii=True) + "\n"
        if path.exists() and path.stat().st_size + len(line.encode("utf-8")) > 262144:
            os.replace(path, previous)
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(line)


def run(
    manager: Manager, identifier: str, action: str, params: dict[str, Any], *,
    invocation_id: str | None = None, cancellation: threading.Event | None = None,
    expected_digest: str | None = None,
    background: bool = False,
) -> dict:
    from hosaka.extensions.manager import digest

    validate_id(identifier)
    validate_id(action)
    invocation = str(uuid.UUID(invocation_id)) if invocation_id else str(uuid.uuid4())
    report: dict = {
        "protocol_version": 1, "invocation_id": invocation, "extension_id": identifier,
        "action": action, "ok": False, "result": None, "error": None,
        "execution_mode": "trusted-local", "sandboxed": False, "duration_ms": 0,
    }
    started = time.monotonic()
    events: list = []
    invoked = False
    try:
        try:
            encoded = json.dumps(params, allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise InvocationError("invalid_input", "Parameters must be bounded JSON values.") from exc
        if not isinstance(params, dict) or len(encoded) > MAX_REQUEST_BYTES:
            raise InvocationError("invalid_input", "Parameters must be a JSON object of at most 16 KiB.")
        info = manager.info(identifier)
        package = validate_package(Path(info["path"]))
        registry = manager.registry()
        entry = registry.extensions.get(identifier)
        reason = approval_reason(package, entry, safe_mode=registry.safe_mode)
        if reason:
            raise InvocationError("not_authorized", reason)
        assert entry is not None and entry.approved_digest is not None
        if expected_digest is not None and expected_digest != entry.approved_digest:
            raise InvocationError("stale_view", "The approved source changed; reopen this extension view.")
        if action not in package.manifest.actions:
            raise InvocationError("unknown_action", "Choose a declared extension action.")
        schema = package.manifest.actions[action]
        _validate_instance(params, read_document(package_file(package.root, schema.input_schema), json_only=True), "input")
        state = _directory(manager, "state/extension-jobs")
        if background and (
            package.manifest.background is None or package.manifest.background.action != action
            or "background:self" not in entry.grants
        ):
            raise InvocationError("not_authorized", "Background execution requires its declared action and explicit grant.")
        with _slots(state, identifier, background):
            data = _directory(manager, f"extension-data/{identifier}")
            if data.resolve().is_relative_to(package.root.resolve()) or package.root.resolve().is_relative_to(data.resolve()):
                raise InvocationError("unsafe_path", "Extension source and persistent data must be separate directories.")
            active = state / f"{identifier}.{invocation}.active"
            marker = state / f"{identifier}.{invocation}.cancel"
            fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            try:
                with tempfile.TemporaryDirectory(prefix="hosaka-extension-code-") as temporary:
                    snapshot = Path(temporary) / "package"
                    shutil.copytree(package.root, snapshot, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"))
                    if digest(snapshot) != entry.approved_digest:
                        raise InvocationError("source_changed", "Source changed while preparing the approved code snapshot.")
                    package = validate_package(snapshot)
                    request = {
                        "protocol_version": 1, "invocation_id": invocation, "extension_id": identifier,
                        "approved_digest": entry.approved_digest, "action": action, "params": params,
                        "package": str(snapshot), "entrypoint": package.manifest.entrypoint.file,
                        "callable": package.manifest.entrypoint.callable,
                        "data_root": str(data), "storage": "storage:self" in entry.grants and package.manifest.permissions.filesystem != "none",
                        "managed": "storage:directory" in entry.grants and package.manifest.permissions.filesystem == "data-directory",
                        "network": "network:self" in entry.grants and package.manifest.permissions.network,
                        "background": background,
                        "max_file_bytes": package.manifest.limits.max_file_bytes,
                        "timeout_seconds": package.manifest.limits.timeout_seconds,
                    }
                    invoked = True
                    response = _process(request, package, manager, marker, cancellation)
                    _still_allowed(manager, identifier, entry.approved_digest, request["storage"],
                                   request["managed"], request["network"], background)
                    if response["error"] is not None:
                        error = response["error"]
                        if not isinstance(error, dict) or error.get("code") != "extension_exception":
                            raise InvocationError("invalid_protocol", "Extension error envelope is malformed.")
                        raise InvocationError("extension_exception", "Extension raised an exception; inspect its trusted source.")
                    result = response["result"]
                    _validate_instance(result, read_document(package_file(snapshot, schema.output_schema), json_only=True), "output")
                    if (
                        not isinstance(result, dict) or type(result.get("success")) is not bool
                        or not isinstance(result.get("message"), str)
                        or (result.get("error") is not None and not isinstance(result["error"], str))
                    ):
                        raise InvocationError("invalid_output", "Results require boolean success, text message and optional text error.")
                    report["result"] = result
                    report["ok"] = result["success"]
                    if not result["success"]:
                        report["error"] = {"code": "action_failed", "message": "Extension returned a controlled failure."}
                    events = response["events"]
            finally:
                active.unlink(missing_ok=True)
                marker.unlink(missing_ok=True)
            report["duration_ms"] = round((time.monotonic() - started) * 1000)
    except (OSError, ExtensionError, ValueError, RecursionError) as exc:
        report["ok"] = False
        report["result"] = None
        report["error"] = {
            "code": exc.code if isinstance(exc, InvocationError) else "invocation_failed",
            "message": str(exc) if isinstance(exc, ExtensionError) else "Runtime configuration or process operation failed; run extensions doctor.",
        }
    finally:
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        if invoked:
            try:
                _record(manager, identifier, report, events)
            except (OSError, ExtensionError):
                report["ok"] = False
                report["result"] = None
                report["error"] = {"code": "logging_failed", "message": "Invocation finished but its bounded log could not be written; inspect extension log permissions."}
    report["duration_ms"] = round((time.monotonic() - started) * 1000)
    return report
