"""Private stdlib-only process bridge, never imported by extension discovery."""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import resource
import stat
import sys
import tempfile
from pathlib import Path

MAX_DATA_BYTES = 65536


class Context:
    def __init__(self, root: Path, storage: bool):
        self.root = root
        self.storage = storage
        self.events: list[dict] = []

    def target(self, name: str) -> Path:
        if not self.storage:
            raise PermissionError("storage:self was not granted")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
            raise ValueError("Use a plain data filename")
        target = self.root / name
        if target.is_symlink() or not target.resolve().is_relative_to(self.root.resolve()):
            raise PermissionError("Data path escapes this extension")
        return target

    def read_data(self, name: str) -> str | None:
        target = self.target(name)
        try:
            fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Data must be a regular file")
            value = stream.read(MAX_DATA_BYTES + 1)
        if len(value) > MAX_DATA_BYTES:
            raise ValueError("Data file exceeds 64 KiB")
        return value.decode("utf-8")

    def write_data(self, name: str, value: str) -> None:
        target = self.target(name)
        if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_DATA_BYTES:
            raise ValueError("Data must be text of at most 64 KiB")
        if not target.exists() and len(list(self.root.iterdir())) >= 128:
            raise ValueError("Extension data directory has reached 128 files")
        fd, temporary = tempfile.mkstemp(prefix=".data-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(value)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def delete_data(self, name: str) -> None:
        self.target(name).unlink(missing_ok=True)

    def log(self, event: str, metadata: dict) -> None:
        if not isinstance(event, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", event):
            raise ValueError("Invalid event name")
        if len(self.events) >= 32 or not isinstance(metadata, dict) or len(metadata) > 8:
            raise ValueError("Too many event fields or events")
        if any(not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key) for key in metadata):
            raise ValueError("Invalid event field name")
        # Values are deliberately excluded from persistent runtime logs.
        self.events.append({"event": event, "metadata_fields": sorted(metadata)})


def main() -> int:
    if os.geteuid() == 0:
        print("Trusted-local workers refuse root.", file=sys.stderr)
        return 3
    request = json.loads(sys.stdin.buffer.read(32769))
    invocation = request["invocation_id"]
    response = {"protocol_version": 1, "invocation_id": invocation, "result": None, "error": None, "events": []}
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (request["timeout_seconds"] + 1, request["timeout_seconds"] + 2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(64, soft), hard))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        package = Path(request["package"])
        context = Context(Path(request["data_root"]), request["storage"])
        sys.path.insert(0, str(package))
        spec = importlib.util.spec_from_file_location("hosaka_extension_entry", package / request["entrypoint"])
        if spec is None or spec.loader is None:
            raise ImportError("Cannot load entrypoint")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        with contextlib.redirect_stdout(sys.stderr):
            spec.loader.exec_module(module)
            function = getattr(module, request["callable"])
            response["result"] = function(request["action"], request["params"], context)
        response["events"] = context.events
        encoded = json.dumps(response, allow_nan=False)
    except Exception as exc:
        # The package exception boundary returns failure, never host success or
        # arbitrary exception text that might contain inputs or credentials.
        response["result"] = None
        response["error"] = {"code": "extension_exception", "message": f"Extension raised {type(exc).__name__}; inspect its trusted source."}
        encoded = json.dumps(response)
    sys.stdout.write(encoded + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
