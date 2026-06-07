from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


APP_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = Path(os.getenv("HOSAKA_APPS_ROOT", str(APP_ROOT / "hosaka-apps")))
APPS_DIR = APPS_ROOT / "apps"
ALIASES_PATH = Path(
    os.getenv(
        "HOSAKA_APP_ALIASES",
        str(Path.home() / ".config" / "hosaka" / "app-aliases.json"),
    ),
)


def normalize_app_token(raw: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", raw.strip().lower()).strip("-")


@dataclass(frozen=True)
class HosakaApp:
    id: str
    name: str
    category: str
    description: str
    flatpak_id: str
    launch_command: list[str]
    install_command: list[str]
    aliases: tuple[str, ...]


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - deployment image has pyyaml
        return _load_manifest_fallback(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_manifest_fallback(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key = ""
    list_keys = {"aliases", "arches", "flatpak_overrides", "permissions_notes", "notes"}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.split(" #", 1)[0].rstrip()
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if value:
                data[current_key] = value.strip("\"'")
            elif current_key in list_keys:
                data[current_key] = []
            else:
                data[current_key] = {}
            continue
        if indent == 2 and current_key in {"install", "launch"} and stripped == "command:":
            section = data.setdefault(current_key, {})
            if isinstance(section, dict):
                section["command"] = []
            continue
        if indent >= 4 and current_key in {"install", "launch"} and stripped.startswith("- "):
            section = data.setdefault(current_key, {})
            if isinstance(section, dict):
                command = section.setdefault("command", [])
                if isinstance(command, list):
                    command.append(stripped[2:].strip().strip("\"'"))
            continue
        if indent >= 2 and current_key in list_keys and stripped.startswith("- "):
            values = data.setdefault(current_key, [])
            if isinstance(values, list):
                values.append(stripped[2:].strip().strip("\"'"))
    return data


def _command(data: dict[str, Any], key: str) -> list[str]:
    raw = data.get(key)
    if not isinstance(raw, dict):
        return []
    command = raw.get("command")
    if not isinstance(command, list):
        return []
    return [str(part) for part in command if str(part)]


def _to_app(data: dict[str, Any]) -> HosakaApp | None:
    app_id = normalize_app_token(str(data.get("id", "")))
    flatpak_id = str(data.get("flatpak_id", "")).strip()
    launch = _command(data, "launch")
    install = _command(data, "install")
    if not app_id or not flatpak_id or not launch:
        return None
    raw_aliases = data.get("aliases")
    aliases = []
    if isinstance(raw_aliases, list):
        aliases = [normalize_app_token(str(alias)) for alias in raw_aliases]
    return HosakaApp(
        id=app_id,
        name=str(data.get("name", app_id)),
        category=str(data.get("category", "other")),
        description=str(data.get("description", "")),
        flatpak_id=flatpak_id,
        launch_command=launch,
        install_command=install,
        aliases=tuple(sorted(set([app_id, *[a for a in aliases if a]]))),
    )


def list_apps() -> list[HosakaApp]:
    if not APPS_DIR.exists():
        return []
    apps: list[HosakaApp] = []
    for path in sorted(APPS_DIR.iterdir()):
        if path.name.startswith(".") or path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        try:
            app = _to_app(_load_yaml(path))
        except (OSError, UnicodeDecodeError, RuntimeError):
            continue
        if app:
            apps.append(app)
    return sorted(apps, key=lambda app: app.name.lower())


def load_aliases() -> dict[str, str]:
    try:
        data = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    aliases: dict[str, str] = {}
    for alias, target in data.items():
        alias_token = normalize_app_token(str(alias))
        target_token = normalize_app_token(str(target))
        if alias_token and target_token:
            aliases[alias_token] = target_token
    return aliases


def save_alias(alias: str, target: str) -> tuple[bool, str]:
    alias_token = normalize_app_token(alias)
    target_app = resolve_app(target)
    if not alias_token:
        return False, "alias is empty"
    if not target_app:
        return False, f"app not found: {target}"
    aliases = load_aliases()
    aliases[alias_token] = target_app.id
    ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALIASES_PATH.write_text(json.dumps(aliases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True, f"{alias_token} -> {target_app.id}"


def resolve_app(raw: str) -> HosakaApp | None:
    token = normalize_app_token(raw)
    aliases = load_aliases()
    token = aliases.get(token, token)
    for app in list_apps():
        if app.id == token or token in app.aliases:
            return app
    return None


def _expand_arg(arg: str) -> str:
    return os.path.expanduser(os.path.expandvars(arg))


def _resolve_graphical_env() -> tuple[dict[str, str], Optional[str], Optional[str]]:
    user = os.getenv("HOSAKA_KIOSK_USER")
    xdg = os.getenv("HOSAKA_KIOSK_XDG_RUNTIME_DIR") or os.getenv("XDG_RUNTIME_DIR")
    wayland = os.getenv("HOSAKA_KIOSK_WAYLAND_DISPLAY") or os.getenv("WAYLAND_DISPLAY")
    display = os.getenv("HOSAKA_KIOSK_DISPLAY") or os.getenv("DISPLAY")
    xauthority = os.getenv("HOSAKA_KIOSK_XAUTHORITY") or os.getenv("XAUTHORITY")
    note: Optional[str] = None

    if not (user and xdg and (wayland or display)):
        try:
            run_user = Path("/run/user")
            candidates = sorted(
                int(p.name) for p in run_user.iterdir() if p.name.isdigit() and int(p.name) >= 1000
            )
        except OSError:
            candidates = []
        for uid in candidates:
            seat = run_user / str(uid)
            try:
                import pwd
                pw = pwd.getpwuid(uid)
            except (KeyError, ImportError):
                continue
            if user is None:
                user = pw.pw_name
            if xdg is None:
                xdg = str(seat)
            if not wayland:
                wls = [p for p in sorted(seat.glob("wayland-*")) if not p.name.endswith(".lock")]
                if wls:
                    wayland = wls[0].name
            break

    if not wayland and not (display and xauthority):
        try:
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                try:
                    comm = (pid_dir / "comm").read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if comm not in {"Xorg", "Xwayland", "X"}:
                    continue
                try:
                    argv = [
                        part.decode("utf-8", "ignore")
                        for part in (pid_dir / "cmdline").read_bytes().split(b"\0")
                        if part
                    ]
                except OSError:
                    continue
                disp_arg = next((arg for arg in argv[1:] if re.fullmatch(r":\d+", arg)), None)
                auth_arg = None
                for idx, arg in enumerate(argv):
                    if arg == "-auth" and idx + 1 < len(argv):
                        auth_arg = argv[idx + 1]
                        break
                if disp_arg and not display:
                    display = disp_arg
                if auth_arg and not xauthority:
                    xauthority = auth_arg
                if display and xauthority:
                    break
        except OSError:
            pass

    if not (user and (wayland or display)):
        note = "no graphical seat found; app may launch headless"

    env: dict[str, str] = {}
    if xdg:
        env["XDG_RUNTIME_DIR"] = xdg
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={xdg}/bus")
    if wayland:
        env["WAYLAND_DISPLAY"] = wayland
    if display:
        env["DISPLAY"] = display
    elif not wayland:
        env["DISPLAY"] = ":0"
    if xauthority:
        env["XAUTHORITY"] = xauthority
    env.setdefault("GTK_USE_PORTAL", "0")
    env.setdefault("GIO_USE_PORTALS", "0")
    return env, user, note


def _sync_user_activation_env(user: Optional[str], env: dict[str, str]) -> None:
    keys = [
        key
        for key in ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
        if env.get(key)
    ]
    if not keys:
        return
    prefix = ["runuser", "-u", user, "--"] if user and os.geteuid() == 0 else []
    base = {**os.environ, **env}
    for command in (
        [*prefix, "systemctl", "--user", "import-environment", *keys],
        [*prefix, "dbus-update-activation-environment", "--systemd", *keys],
        [*prefix, "systemctl", "--user", "reset-failed", "xdg-desktop-portal-gtk.service", "xdg-desktop-portal.service"],
    ):
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
                env=base,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def _flatpak_installed(app: HosakaApp) -> bool:
    if not shutil.which("flatpak"):
        return False
    result = subprocess.run(  # noqa: S603
        ["flatpak", "info", app.flatpak_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def launch_app(app: HosakaApp) -> tuple[bool, str]:
    if not shutil.which("flatpak"):
        return False, "flatpak is not installed"
    if not _flatpak_installed(app):
        install = " ".join(app.install_command) if app.install_command else f"flatpak install flathub {app.flatpak_id}"
        return False, f"{app.name} is not installed. install: {install}"
    command = [_expand_arg(part) for part in app.launch_command]
    seat_env, seat_user, note = _resolve_graphical_env()
    _sync_user_activation_env(seat_user, seat_env)
    try:
        subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, **seat_env},
        )
    except (OSError, FileNotFoundError) as exc:
        return False, f"launch failed: {exc}"
    message = f"launched {app.name}"
    if note:
        message += f" ({note})"
    return True, message


def print_app_list() -> None:
    apps = list_apps()
    aliases = load_aliases()
    if not apps:
        print("No Hosaka app manifests found.")
        return
    print("Launchable Hosaka apps:")
    for app in apps:
        installed = "installed" if _flatpak_installed(app) else "not installed"
        user_aliases = sorted(alias for alias, target in aliases.items() if target == app.id)
        suffix = f" aliases: {', '.join(user_aliases)}" if user_aliases else ""
        print(f"  {app.id:16} {app.name:24} {app.category:12} {installed}{suffix}")
    print("")
    print("Use: hosaka launch <app>")
    print("Alias: hosaka launch alias <short-name> <app>")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hosaka launch", add_help=False)
    parser.add_argument("args", nargs="*")
    ns = parser.parse_args(argv)
    args = ns.args
    if not args or args[0] in {"list", "ls", "apps", "--help", "-h", "help"}:
        print_app_list()
        return 0
    if args[0] in {"alias", "aliases"}:
        if len(args) == 1:
            aliases = load_aliases()
            if not aliases:
                print(f"No aliases yet. Add one with: hosaka launch alias ff firefox")
                return 0
            for alias, target in sorted(aliases.items()):
                print(f"{alias} -> {target}")
            return 0
        if len(args) != 3:
            print("usage: hosaka launch alias <alias> <app>", file=sys.stderr)
            return 2
        ok, message = save_alias(args[1], args[2])
        print(message)
        return 0 if ok else 2
    app = resolve_app(args[0])
    if not app:
        print(f"app not found: {args[0]}", file=sys.stderr)
        print_app_list()
        return 2
    ok, message = launch_app(app)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
