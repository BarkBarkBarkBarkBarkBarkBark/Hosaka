"""Package lifecycle metadata. No extension code, hooks or tests execute here."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Literal

from pydantic import Field, ValidationError, field_validator
import yaml

from hosaka.paths import CORE_ROOT, HosakaPaths, resolve_paths
from hosaka.extensions.manifest import (
    ExtensionError, Package, StrictModel, read_document, validate_id, validate_package,
)

REFERENCE = CORE_ROOT / "examples/extensions/reference-extension"


class Registration(StrictModel):
    path: str
    version: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled: bool = False
    removed: bool = False
    grants: list[Literal["storage:self", "storage:directory", "network:self", "background:self"]] = Field(default_factory=list)
    execution_mode: Literal["trusted-local"] | None = None
    approved_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class Registry(StrictModel):
    schema_version: Literal[1] = 1
    safe_mode: bool = False
    extensions: dict[str, Registration] = Field(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Registry version must be an integer")
        return value


def digest(root: Path) -> str:
    result = hashlib.sha256()
    count, total = 0, 0
    for path in sorted(root.rglob("*")):
        if any(part in {".git", "__pycache__", ".pytest_cache", ".venv"} for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ExtensionError("Package copies and registration do not accept symlinks; use regular files.")
        if path.is_file():
            count += 1
            total += path.stat().st_size
            if count > 4096 or total > 32 * 1024 * 1024:
                raise ExtensionError("Package exceeds 4096 files or 32 MiB; keep dependencies/data outside package source.")
            result.update(str(path.relative_to(root)).encode())
            result.update(b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    result.update(chunk)
            result.update(b"\0")
        elif not path.is_dir():
            raise ExtensionError("Packages may contain only regular files and directories.")
    return result.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".extensions-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Manager:
    def __init__(self, paths: HosakaPaths | None = None):
        self.paths = paths or resolve_paths()
        self.root = self.paths.root
        self.packages = self.root / "extensions"
        self.lock = self.root / "extensions.lock.json"

    def registry(self) -> Registry:
        if self.lock.is_symlink():
            raise ExtensionError("Extension registry must not be a symlink.")
        if not self.lock.exists():
            return Registry()
        try:
            result = Registry.model_validate(read_document(self.lock, json_only=True))
        except ValidationError as exc:
            raise ExtensionError("Invalid extensions.lock.json; restore it from backup, do not reset it.") from exc
        registered_paths = set()
        for identifier, entry in result.extensions.items():
            validate_id(identifier)
            if not Path(entry.path).is_absolute():
                raise ExtensionError("Registered extension paths must be absolute.")
            resolved = Path(entry.path).resolve()
            if resolved in registered_paths:
                raise ExtensionError("Multiple extension IDs reference the same package directory.")
            registered_paths.add(resolved)
        return result

    @contextmanager
    def transaction(self) -> Generator[Registry, None, None]:
        if os.getuid() != self.paths.operator.uid:
            raise ExtensionError("Manage extensions as the selected operator, not another account.")
        for core in (CORE_ROOT, *(
            Path(self.paths.installation[key]) for key in ("repo_root", "runtime_root") if key in self.paths.installation
        )):
            if self.root.resolve().is_relative_to(core.resolve()):
                raise ExtensionError("Extension storage must be outside the core checkout and deployment.")
        for directory in self.paths.directories().values():
            if not directory.resolve().is_relative_to(self.root):
                raise ExtensionError("Managed extension directory escapes the data root.")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (self.root / ".extensions.lock").is_symlink():
            raise ExtensionError("Extension transaction lock must not be a symlink.")
        self.root.chmod(0o700)
        with (self.root / ".extensions.lock").open("a", encoding="utf-8") as stream:
            os.chmod(stream.name, 0o600)
            fcntl.flock(stream, fcntl.LOCK_EX)
            registry = self.registry()
            yield registry
            _atomic_json(self.lock, registry.model_dump())

    def discover(self) -> dict:
        from hosaka.extensions.runner import approval_reason

        registry = self.registry()
        candidates: dict[Path, Registration | None] = {
            Path(entry.path).resolve(): entry for entry in registry.extensions.values() if not entry.removed
        }
        removed = {Path(entry.path).resolve() for entry in registry.extensions.values() if entry.removed}
        if self.packages.is_dir():
            for path in sorted(self.packages.iterdir()):
                if path.is_dir() and not path.name.startswith("."):
                    if path.resolve() not in removed:
                        candidates.setdefault(path.resolve(), None)
        found: list[dict] = []
        errors: list[dict] = []
        identities: dict[str, list[dict]] = {}
        for path, registration in candidates.items():
            try:
                package = validate_package(path)
                identifier = package.manifest.id
                if registration is not None and registry.extensions.get(identifier) is not registration:
                    raise ExtensionError("Registered package identity changed; repair explicitly before enabling.")
                reason = approval_reason(package, registration, safe_mode=registry.safe_mode)
                item = {
                    "id": identifier, "name": package.manifest.name,
                    "version": package.manifest.version, "path": str(path),
                    "registered": registration is not None,
                    "enabled": registration.enabled if registration else False,
                    "grants": registration.grants if registration else [],
                    "execution_available": reason is None, "ui_available": bool(registration and registration.enabled),
                    "execution_reason": reason,
                    "execution_mode": registration.execution_mode if registration else None,
                    "approved_digest": registration.approved_digest if registration else None,
                    "menu": package.manifest.menu.model_dump(),
                    "actions": list(package.manifest.actions),
                    "registered_version": registration.version if registration else None,
                }
                identities.setdefault(identifier, []).append(item)
                found.append(item)
            except (ExtensionError, OSError) as exc:
                errors.append({"path": str(path), "error": str(exc)})
        duplicates = {identifier for identifier, items in identities.items() if len(items) > 1}
        for identifier in sorted(duplicates):
            for item in identities[identifier]:
                errors.append({"path": item["path"], "error": f"Duplicate extension ID: {identifier}"})
        return {
            "schema_version": 1,
            "extensions": [item for item in found if item["id"] not in duplicates],
            "errors": errors, "execution_available": any(item["execution_available"] for item in found if item["id"] not in duplicates),
            "ui_available": True, "safe_mode": registry.safe_mode or os.getenv("HOSAKA_EXTENSIONS_SAFE_MODE", "").lower() in {"1", "true", "yes", "on"},
        }

    def _register(self, registry: Registry, package: Package) -> None:
        identifier = package.manifest.id
        existing = registry.extensions.get(identifier)
        if existing and Path(existing.path).resolve() != package.root:
            raise ExtensionError(f"Extension ID is already registered: {identifier}")
        discovered = self.discover()
        for item in discovered["extensions"]:
            if item["id"] == identifier and Path(item["path"]) != package.root:
                raise ExtensionError(f"Extension ID already exists in another package: {identifier}")
        if any(
            error["error"] == f"Duplicate extension ID: {identifier}"
            for error in discovered["errors"]
        ):
            raise ExtensionError(f"Duplicate extension ID: {identifier}; repair the package directories first.")
        package_digest = digest(package.root)
        if not existing:
            registry.extensions[identifier] = Registration(
                path=str(package.root), version=package.manifest.version, digest=package_digest,
            )
        else:
            existing.removed = False

    def init(self) -> dict:
        reference = validate_package(REFERENCE)
        with self.transaction() as registry:
            destination = self.packages / reference.manifest.id
            existing = registry.extensions.get(reference.manifest.id)
            if existing and existing.removed:
                return {
                    "reference": existing.path, "seeded": False,
                    "message": "Reference was removed by the owner; initialization preserves that choice.",
                    **self.discover(),
                }
            if existing:
                destination = Path(existing.path)
            seeded = not destination.exists()
            if seeded:
                self._copy(REFERENCE, destination, reference.manifest.id)
            installed = validate_package(destination)
            if installed.manifest.id != reference.manifest.id:
                raise ExtensionError("Existing reference folder has another ID; it was not overwritten.")
            self._register(registry, installed)
            different = digest(destination) != digest(REFERENCE)
        return {
            "reference": str(destination), "seeded": seeded,
            "reference_differs": different,
            "message": "Existing reference preserved; differs from shipped template." if different else "Reference validated.",
            **self.discover(),
        }

    def _copy(self, template: Path, destination: Path, identifier: str) -> None:
        if destination.exists() or destination.is_symlink():
            raise ExtensionError("Refusing to overwrite an existing extension path.")
        digest(template)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix=".extension-stage-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "package"
            shutil.copytree(template, staged, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".venv"))
            manifest = staged / "extension.yaml"
            values = read_document(manifest)
            if values["id"] != identifier:
                label = identifier.replace("-", " ").title()
                values["id"] = identifier
                values["name"] = label
                values["menu"]["label"] = label
                manifest.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
            validate_package(staged)
            staged.rename(destination)

    def create(self, identifier: str, destination: Path | None = None) -> dict:
        validate_id(identifier)
        destination = (destination or self.packages / identifier).expanduser().absolute()
        self._outside_core(destination)
        with self.transaction() as registry:
            if identifier in registry.extensions:
                raise ExtensionError("Extension ID is already registered.")
            # Validate identity collisions before creating anything.
            if any(item["id"] == identifier for item in self.discover()["extensions"]):
                raise ExtensionError("Extension ID already exists.")
            self._copy(REFERENCE, destination, identifier)
            self._register(registry, validate_package(destination))
        return self.info(identifier)

    def _outside_core(self, path: Path) -> None:
        for core in (CORE_ROOT, *(
            Path(self.paths.installation[key]) for key in ("repo_root", "runtime_root") if key in self.paths.installation
        )):
            if path.resolve().is_relative_to(core.resolve()):
                raise ExtensionError("Extension working copies must be outside core.")

    def link(self, path: Path) -> dict:
        self._outside_core(path)
        package = validate_package(path)
        with self.transaction() as registry:
            self._register(registry, package)
        return self.info(package.manifest.id)

    def info(self, identifier: str) -> dict:
        validate_id(identifier)
        report = self.discover()
        items = [item for item in report["extensions"] if item["id"] == identifier]
        if not items:
            raise ExtensionError(f"Extension not available: {identifier}. Run extensions doctor for diagnostics.")
        item = items[0]
        package = validate_package(Path(item["path"]))
        registration = self.registry().extensions.get(identifier)
        return {
            **item, "manifest": package.manifest.model_dump(), "ui": package.view,
            "data_path": str(self.root / "extension-data" / identifier),
            "source_modified": digest(package.root) != registration.digest if registration else None,
        }

    def enable(self, identifier: str, enabled: bool) -> dict:
        validate_id(identifier)
        if not enabled:
            # Safety controls must remain usable when package source is broken.
            with self.transaction() as registry:
                entry = registry.extensions.get(identifier)
                if entry is None:
                    raise ExtensionError("Extension is not registered.")
                entry.enabled = False
            return {"id": identifier, "enabled": False, "removed": entry.removed}
        info = self.info(identifier)
        with self.transaction() as registry:
            self._register(registry, validate_package(Path(info["path"])))
            registry.extensions[identifier].enabled = enabled
        return self.info(identifier)

    def remove(self, identifier: str) -> dict:
        validate_id(identifier)
        with self.transaction() as registry:
            entry = registry.extensions.get(identifier)
            if entry is None:
                raise ExtensionError("Extension is not registered.")
            # Unregister, never recursively delete package code or saved data.
            entry.removed = True
            entry.enabled = False
        return {"id": identifier, "removed": True, "code_retained": True, "data_retained": True}

    def trust(self, identifier: str, *, allow_storage: bool = False, allow_managed_data: bool = False,
              allow_network: bool = False, allow_background: bool = False) -> dict:
        if os.geteuid() == 0:
            raise ExtensionError("Trusted-local approval refuses root; use the unprivileged operator.")
        info = self.info(identifier)
        package = validate_package(Path(info["path"]))
        if allow_managed_data and package.manifest.permissions.filesystem != "data-directory":
            raise ExtensionError("Package does not request managed data-directory access.")
        if allow_network and not package.manifest.permissions.network:
            raise ExtensionError("Package does not request network access.")
        if allow_background and package.manifest.background is None:
            raise ExtensionError("Package does not declare a background action.")
        with self.transaction() as registry:
            self._register(registry, package)
            entry = registry.extensions[identifier]
            entry.execution_mode = "trusted-local"
            entry.approved_digest = digest(package.root)
            entry.grants = [
                name for name, granted in (
                    ("storage:self", allow_storage), ("storage:directory", allow_managed_data),
                    ("network:self", allow_network), ("background:self", allow_background),
                ) if granted
            ]
        return {
            **self.info(identifier),
            "warning": "Approved code runs with your user privileges. This is NOT an OS sandbox. Enablement remains separate.",
        }

    def revoke(self, identifier: str) -> dict:
        validate_id(identifier)
        with self.transaction() as registry:
            entry = registry.extensions.get(identifier)
            if entry is None:
                raise ExtensionError("Extension is not registered.")
            entry.approved_digest = None
            entry.execution_mode = None
            entry.grants = []
        return {"id": identifier, "approval_revoked": True, "grants": []}

    def safe_mode(self, setting: str) -> dict:
        if setting not in {"on", "off", "status"}:
            raise ExtensionError("Safe mode must be on, off or status.")
        if setting != "status":
            with self.transaction() as registry:
                registry.safe_mode = setting == "on"
        saved = self.registry().safe_mode
        environment = os.getenv("HOSAKA_EXTENSIONS_SAFE_MODE", "").lower() in {"1", "true", "yes", "on"}
        return {"safe_mode": saved or environment, "saved_safe_mode": saved, "environment_override": environment}

    def doctor(self) -> dict:
        report = self.discover()
        report["paths"] = {
            name: {
                "path": str(path), "exists": path.is_dir(),
                "escapes_data_root": not path.resolve().is_relative_to(self.root),
                "uid": path.stat().st_uid if path.exists() else None,
                "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}" if path.exists() else None,
            }
            for name, path in self.paths.directories().items()
        }
        for directory in report["paths"].values():
            if directory["escapes_data_root"]:
                report["errors"].append({"path": directory["path"], "error": "Managed directory escapes data root."})
        report["registry_present"] = self.lock.is_file()
        report["status"] = "fail" if report["errors"] else "warn" if (
            not report["registry_present"] or any(not item["exists"] for item in report["paths"].values())
            or report["paths"]["data"]["mode"] != "0700"
        ) else "pass"
        report["limitations"] = [
            "Trusted-local execution is not an OS sandbox; approved code retains user privileges.",
            "Root/public execution is refused; OS-enforced Linux containment remains pending.",
            "Approval is digest-bound; enablement and storage grants are separate.",
        ]
        return report
