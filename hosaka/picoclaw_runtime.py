"""Generate PicoClaw runtime files from Hosaka-owned source files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DIR = REPO_ROOT / "identity"

IDENTITY_FILES = {
    "AGENT.md": IDENTITY_DIR / "AGENT.md",
    "AGENTS.md": IDENTITY_DIR / "AGENT.md",
    "IDENTITY.md": IDENTITY_DIR / "AGENT.md",
    "SOUL.md": IDENTITY_DIR / "SOUL.md",
    "USER.md": IDENTITY_DIR / "USER.md",
}

TASKS_STUB = """# Hosaka Task State

This is the live runtime task state for Hosaka manager mode.

Policy lives in `/home/operator/manager.yaml`.
Runtime state lives here so the PicoClaw runtime can update it without
depending on root-owned files outside `~/.picoclaw`.
"""


def _write_generated_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current == content:
            return
    path.write_text(content, encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _seed_config(home: Path) -> dict[str, Any]:
    workspace = str(home / ".picoclaw" / "workspace")
    return {
        "session": {"dm_scope": "per-channel-peer"},
        "version": 2,
        "agents": {
            "defaults": {
                "workspace": workspace,
                "restrict_to_workspace": False,
                "allow_read_outside_workspace": True,
                "model_name": "gpt-4o-mini",
                "max_tokens": 16384,
                "max_tool_iterations": 50,
            }
        },
        "model_list": [
            {
                "model_name": "gpt-4o-mini",
                "model": "openai/gpt-4o-mini",
                "api_key": "",
                "api_base": "https://api.openai.com/v1",
            }
        ],
        "gateway": {"host": "127.0.0.1", "port": 18790, "log_level": "warn"},
        "tools": {
            "allow_read_paths": ["/"],
            "allow_write_paths": [str(home), "/tmp"],
        },
    }


def ensure_picoclaw_runtime(home: str | Path | None = None, seed_config: bool = False) -> None:
    home_path = Path(home).expanduser() if home else Path.home()
    pico_home = home_path / ".picoclaw"
    workspace = pico_home / "workspace"
    memory_dir = workspace / "memory"

    pico_home.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    for name, src in IDENTITY_FILES.items():
        _write_generated_file(workspace / name, src.read_text(encoding="utf-8"))

    tasks_path = memory_dir / "TASKS.md"
    if tasks_path.is_symlink():
        tasks_path.unlink()
    if not tasks_path.exists():
        tasks_path.write_text(TASKS_STUB, encoding="utf-8")

    config_path = pico_home / "config.json"
    if not config_path.exists() and seed_config:
        config = _seed_config(home_path)
    else:
        config = _load_json(config_path)
        if not config:
            if not seed_config:
                return
            config = _seed_config(home_path)

    defaults = config.setdefault("agents", {}).setdefault("defaults", {})
    defaults["workspace"] = str(workspace)
    defaults.setdefault("restrict_to_workspace", False)
    defaults.setdefault("allow_read_outside_workspace", True)
    defaults.setdefault("model_name", "gpt-4o-mini")
    defaults.setdefault("max_tokens", 16384)
    defaults.setdefault("max_tool_iterations", 50)

    gateway = config.setdefault("gateway", {})
    gateway.setdefault("host", "127.0.0.1")
    gateway.setdefault("port", 18790)

    tools = config.setdefault("tools", {})
    read_paths = tools.setdefault("allow_read_paths", ["/"])
    if "/" not in read_paths:
        read_paths.append("/")
    write_paths = tools.setdefault("allow_write_paths", [])
    for candidate in (str(home_path), "/tmp"):
        if candidate not in write_paths:
            write_paths.append(candidate)

    if seed_config and "model_list" not in config:
        config["model_list"] = _seed_config(home_path)["model_list"]

    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PicoClaw runtime files from Hosaka source")
    parser.add_argument("--home", default=os.path.expanduser("~"))
    parser.add_argument("--seed-config", action="store_true")
    args = parser.parse_args()
    ensure_picoclaw_runtime(home=args.home, seed_config=args.seed_config)


if __name__ == "__main__":
    main()
