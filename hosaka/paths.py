"""Operator paths and nonsecret installation records; no provider probes."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CORE_ROOT = Path(__file__).resolve().parents[1]
ROM_EXTENSIONS = (".m3u", ".cue", ".chd", ".pbp", ".iso")


@dataclass(frozen=True)
class Operator:
    name: str
    home: Path
    uid: int
    gid: int


def resolve_operator() -> Operator:
    import pwd

    name = os.environ.get("HOSAKA_OPERATOR") or os.environ.get("SUDO_USER")
    current = pwd.getpwuid(os.getuid())
    try:
        account = pwd.getpwnam(name) if name else current
    except KeyError as exc:
        raise ValueError(f"Unknown Hosaka operator: {name}") from exc
    # A normal user may intentionally supply HOME (e.g. isolated installation).
    # Under sudo, never mistake root's HOME for the selected operator's home.
    home = Path.home() if account.pw_uid == os.getuid() and not os.environ.get("SUDO_USER") else Path(account.pw_dir)
    if not home.is_absolute():
        raise ValueError("The operator home must be an absolute path.")
    return Operator(account.pw_name, home.resolve(), account.pw_uid, account.pw_gid)


def _path(raw: str, home: Path, *, resolve_symlinks: bool = True) -> Path:
    if raw == "~":
        result = home
    elif raw.startswith("~/"):
        result = home / raw[2:]
    else:
        result = Path(raw)
    if not raw.strip() or not result.is_absolute():
        raise ValueError("Hosaka paths must be absolute or start with ~/ for the selected operator.")
    return result.resolve() if resolve_symlinks else result.absolute()


def data_root(operator: Operator | None = None) -> Path:
    operator = operator or resolve_operator()
    raw = os.environ.get("HOSAKA_DATA_DIR")
    return _path(raw, operator.home) if raw is not None else operator.home / ".hosaka"


def _read_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        result = json.loads(text)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Invalid JSON at {path}; repair or restore this file.") from exc
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object at {path}.")
    return result


def _setting(values: dict[str, Any], key: str, home: Path, *, resolve_symlinks: bool = True) -> Path | None:
    if key not in values:
        return None
    value = values[key]
    if not isinstance(value, str):
        raise ValueError(f"Path setting {key} must be a string.")
    return _path(value, home, resolve_symlinks=resolve_symlinks)


def read_installation(root: Path, operator: Operator) -> dict[str, Any]:
    path = root / "installation.json"
    record = _read_object(path)
    if not record and not path.exists():
        return {}
    if type(record.get("schema_version")) is not int or record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported installation record at {path}.")
    if record.get("mode") not in ("source", "appliance", "docker"):
        raise ValueError(f"Invalid installation mode at {path}.")
    if record.get("operator") != operator.name or record.get("home") != str(operator.home):
        raise ValueError(f"Installation at {path} belongs to a different operator/home.")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "mode": record["mode"],
        "operator": operator.name, "home": str(operator.home),
    }
    for key in ("repo_root", "runtime_root", "python", "launcher", "games_dir", "psx_roms"):
        value = _setting(record, key, operator.home, resolve_symlinks=key not in {"python", "launcher"})
        if value is None:
            raise ValueError(f"Installation record at {path} is missing {key}.")
        result[key] = str(value)
    if record.get("picoclaw") is not None:
        result["picoclaw"] = str(_setting(record, "picoclaw", operator.home, resolve_symlinks=False))
    else:
        result["picoclaw"] = None
    return result


def _discover_roms(home: Path, canonical: Path) -> Path:
    candidates = (home / "RetroPie/roms/psx", home / "Games/PlayStation", home / "Games/psx")
    # An empty earlier directory must not hide a populated existing library.
    for path in candidates:
        if path.is_dir() and any(p.is_file() and p.suffix.lower() in ROM_EXTENSIONS for p in path.rglob("*")):
            return path
    return next((path for path in candidates if path.is_dir()), canonical)


@dataclass(frozen=True)
class HosakaPaths:
    operator: Operator
    root: Path
    games: Path
    psx_roms: Path
    installation: dict[str, Any]

    def directories(self) -> dict[str, Path]:
        return {
            "data": self.root,
            "extensions": self.root / "extensions",
            "extension_data": self.root / "extension-data",
            "state": self.root / "state",
            "logs": self.root / "logs",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "operator": {
                "name": self.operator.name, "home": str(self.operator.home),
                "uid": self.operator.uid, "gid": self.operator.gid,
            },
            "paths": {
                **{key: str(value) for key, value in self.directories().items()},
                "core": str(CORE_ROOT),
                "config": str(self.root / "config.json"),
                "installation": str(self.root / "installation.json"),
                "secrets": str(self.root / "secrets.json"),
                "providers": str(self.root / "providers.json"),
                "picoclaw_config": str(self.root / "picoclaw/config.json"),
                "picoclaw_workspace": str(self.root / "picoclaw/workspace"),
                "extension_lock": str(self.root / "extensions.lock.json"),
                "games": str(self.games),
                "psx_roms": str(self.psx_roms),
            },
            "installation": self.installation or None,
        }


def resolve_paths() -> HosakaPaths:
    operator = resolve_operator()
    root = data_root(operator)
    config = _read_object(root / "config.json")
    settings = config.get("paths", {})
    if not isinstance(settings, dict):
        raise ValueError(f"paths must be an object in {root / 'config.json'}.")
    record = read_installation(root, operator)
    games_override = os.environ.get("HOSAKA_GAMES_DIR")
    configured_games = _setting(settings, "games_dir", operator.home)
    games = (
        _path(games_override, operator.home) if games_override is not None
        else configured_games or _setting(record, "games_dir", operator.home) or operator.home / "Games/Hosaka"
    )
    rom_override = os.environ.get("HOSAKA_PSX_ROMS")
    configured_roms = _setting(settings, "psx_roms", operator.home)
    if rom_override is not None:
        roms = _path(rom_override, operator.home)
    elif configured_roms is not None:
        roms = configured_roms
    elif games_override is not None or configured_games is not None:
        roms = games / "roms/psx"
    else:
        roms = _setting(record, "psx_roms", operator.home) or _discover_roms(operator.home, games / "roms/psx")
    return HosakaPaths(operator, root, games, roms.resolve(), record)


def _write_record(path: Path, record: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".installation-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initialize(paths: HosakaPaths, *, mode: str, repo: Path, runtime: Path, launcher: Path, python: Path) -> None:
    if os.getuid() != paths.operator.uid:
        raise ValueError("Initialize as the selected operator (sudo -u USER -H), not as another account.")
    if mode not in {"source", "appliance", "docker"}:
        raise ValueError("Installation mode must be source, appliance or docker.")
    if paths.installation and paths.installation["mode"] != mode:
        raise ValueError("Refusing to replace another installation mode; select a separate HOSAKA_DATA_DIR.")
    for content in (paths.root, paths.games, paths.psx_roms):
        if any(content.resolve().is_relative_to(core.resolve()) for core in (CORE_ROOT, repo, runtime)):
            raise ValueError("User data and games must live outside the source and installed core.")
    for core in (repo, runtime):
        if not (core / "hosaka").is_dir():
            raise ValueError(f"Core package directory is missing: {core / 'hosaka'}")
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError(f"Python executable is missing or not executable: {python}")
    for directory in paths.directories().values():
        if not directory.resolve().is_relative_to(paths.root):
            raise ValueError(f"Managed directory escapes the data root: {directory}")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Bind mounts retain the host owner's UID; do not chown user content.
        if directory.stat().st_uid != paths.operator.uid and mode != "docker":
            raise ValueError(f"Directory is not owned by the selected operator: {directory}")
        if not os.access(directory, os.W_OK):
            raise ValueError(f"Directory is not writable: {directory}")
    paths.root.chmod(0o700)
    paths.games.mkdir(parents=True, exist_ok=True, mode=0o700)
    if paths.psx_roms.is_relative_to(paths.games):
        paths.psx_roms.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {
        "schema_version": SCHEMA_VERSION, "mode": mode,
        "operator": paths.operator.name, "home": str(paths.operator.home),
        "repo_root": str(repo.resolve()), "runtime_root": str(runtime.resolve()),
        # Keep a venv's lexical executable path; resolving its symlink loses the venv.
        "python": str(python.absolute()), "launcher": str(launcher.absolute()),
        "picoclaw": shutil.which("picoclaw"),
        "games_dir": str(paths.games), "psx_roms": str(paths.psx_roms),
    }
    _write_record(paths.root / "installation.json", record)


def executable_candidates(name: str) -> list[str]:
    result: list[str] = []
    for directory in os.get_exec_path():
        candidate = Path(directory or os.curdir).absolute() / name
        if candidate.is_file() and os.access(candidate, os.X_OK) and str(candidate) not in result:
            result.append(str(candidate))
    return result


def offline_report() -> dict[str, Any]:
    paths = resolve_paths()
    checks: list[dict[str, str]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})

    check("installation", "pass" if paths.installation else "warn",
          "Installation record present." if paths.installation else "No installation record; rerun setup.")
    for name, directory in paths.directories().items():
        if not directory.is_dir():
            check(name, "warn", f"Missing directory: {directory}")
        elif not directory.resolve().is_relative_to(paths.root):
            check(name, "fail", f"Managed directory escapes the data root: {directory}")
        elif directory.stat().st_uid != paths.operator.uid and paths.installation.get("mode") != "docker":
            check(name, "fail", f"Wrong owner: {directory}")
        elif not os.access(directory, os.W_OK):
            check(name, "fail", f"Directory is not writable by this process: {directory}")
        else:
            check(name, "pass", str(directory))
    if paths.root.exists() and paths.root.stat().st_mode & 0o077:
        check("data.permissions", "fail", f"Expected private mode 0700: {paths.root}")
    for name in ("hosaka", "picoclaw"):
        candidates = executable_candidates(name)
        implementations = {str(Path(candidate).resolve()) for candidate in candidates}
        check(f"binary.{name}", "pass" if len(implementations) == 1 else "warn",
              ", ".join(candidates) if candidates else f"{name} is not on PATH.")
    for key in ("repo_root", "runtime_root", "python", "launcher", "picoclaw"):
        value = paths.installation.get(key)
        if value:
            target = Path(value)
            valid = target.is_dir() if key.endswith("_root") else target.is_file() and os.access(target, os.X_OK)
            check(f"record.{key}", "pass" if valid else "fail", str(target))
    check("games.psx_roms", "pass" if paths.psx_roms.is_dir() else "warn", str(paths.psx_roms))
    return {
        **paths.as_dict(), "checks": checks, "provider_request_verified": False,
        "overall_status": "fail" if any(c["status"] == "fail" for c in checks)
        else "warn" if any(c["status"] == "warn" for c in checks) else "pass",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    init = subparsers.add_parser("init", help="Initialize external data directories and installation record")
    init.add_argument("--mode", choices=["source", "appliance", "docker"], required=True)
    init.add_argument("--repo-root", type=Path, required=True)
    init.add_argument("--runtime-root", type=Path, required=True)
    init.add_argument("--launcher", type=Path, required=True)
    init.add_argument("--python", type=Path, default=Path(sys.executable))
    args = parser.parse_args(argv)
    try:
        paths = resolve_paths()
        if args.command == "init":
            initialize(paths, mode=args.mode, repo=args.repo_root, runtime=args.runtime_root,
                       launcher=args.launcher, python=args.python)
            paths = resolve_paths()
        result = paths.as_dict()
    except (OSError, ValueError) as exc:
        print(f"Hosaka paths failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"operator: {paths.operator.name} ({paths.operator.home})")
        for name, value in result["paths"].items():
            print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
