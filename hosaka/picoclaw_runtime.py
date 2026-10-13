"""Generate PicoClaw runtime files from Hosaka-owned source files."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hosaka.llm.llm_config import OPENAI_DEFAULT_MODEL

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DIR = REPO_ROOT / "identity"
MANAGER_DIR = REPO_ROOT / "manager"
SKILLS_DIR = REPO_ROOT / "skills"
OLLAMA_DEFAULT_BASE_URL = "http://100.78.174.79:11434/v1"
OLLAMA_DEFAULT_API_KEY = "ollama"
OLLAMA_DEFAULT_MODEL = "qwen2.5:0.5b"
OLLAMA_DEFAULT_ALIAS = "qwen2.5"

IDENTITY_FILES = {
    "AGENT.md": IDENTITY_DIR / "AGENT.md",
    "AGENTS.md": IDENTITY_DIR / "AGENT.md",
    "IDENTITY.md": IDENTITY_DIR / "AGENT.md",
    "SOUL.md": IDENTITY_DIR / "SOUL.md",
    "USER.md": IDENTITY_DIR / "USER.md",
}

MANAGER_FILES = {
    "charter.yaml": MANAGER_DIR / "charter.yaml",
}

SKILL_FILES = {
    "catalog/index.yaml": SKILLS_DIR / "index.yaml",
    "hosaka-task-manager/SKILL.md": SKILLS_DIR / "hosaka-task-manager" / "SKILL.md",
    "hosaka-skill-lifecycle/SKILL.md": SKILLS_DIR / "hosaka-skill-lifecycle" / "SKILL.md",
    "hosaka-games/SKILL.md": SKILLS_DIR / "hosaka-games" / "SKILL.md",
}

TASKS_TEMPLATE_PATH = MANAGER_DIR / "bootstrap_tasks.md"


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
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(config, dict):
        raise ValueError(f"PicoClaw configuration must be an object: {path}")
    return config


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _seed_config(home: Path) -> dict[str, Any]:
    workspace = str(home / ".picoclaw" / "workspace")
    local_first = os.getenv("HOSAKA_LOCAL_FIRST", "0").strip().lower() in ("1", "true", "yes", "on")
    alias = OLLAMA_DEFAULT_ALIAS if local_first else OPENAI_DEFAULT_MODEL
    return {
        "session": {"dimensions": ["chat"]},
        "version": 3,
        "agents": {
            "defaults": {
                "workspace": workspace,
                "restrict_to_workspace": False,
                "allow_read_outside_workspace": True,
                "model_name": alias,
                "max_tokens": 16384,
                "max_tool_iterations": 50,
            }
        },
        "model_list": [
            {
                "model_name": alias,
                "model": f"ollama/{OLLAMA_DEFAULT_MODEL}" if local_first else f"openai/{OPENAI_DEFAULT_MODEL}",
                "api_base": OLLAMA_DEFAULT_BASE_URL if local_first else "https://api.openai.com/v1",
            }
        ],
        "gateway": {"host": "127.0.0.1", "port": 18790, "log_level": "warn"},
        "tools": {
            "allow_read_paths": ["/"],
            "allow_write_paths": [str(home), "/tmp"],
            "find_skills": {"enabled": True},
            "install_skill": {"enabled": True},
            "skills": {
                "enabled": True,
                "registries": {
                    "clawhub": {
                        "enabled": True,
                        "base_url": "https://clawhub.ai",
                        "search_path": "",
                        "skills_path": "",
                        "download_path": "",
                    }
                },
            },
        },
    }


def ensure_picoclaw_runtime(home: str | Path | None = None, seed_config: bool = False) -> None:
    home_path = Path(home).expanduser() if home else Path.home()
    pico_home = home_path / ".picoclaw"
    workspace = pico_home / "workspace"
    memory_dir = workspace / "memory"
    manager_dir = workspace / "manager"
    skills_dir = workspace / "skills"

    pico_home.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)
    manager_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    for name, src in IDENTITY_FILES.items():
        _write_generated_file(workspace / name, _read_text(src))

    for name, src in MANAGER_FILES.items():
        _write_generated_file(manager_dir / name, _read_text(src))

    for name, src in SKILL_FILES.items():
        _write_generated_file(skills_dir / name, _read_text(src))

    tasks_path = memory_dir / "TASKS.md"
    if tasks_path.is_symlink():
        tasks_path.unlink()
    if not tasks_path.exists():
        tasks_path.write_text(_read_text(TASKS_TEMPLATE_PATH), encoding="utf-8")

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
    local_first = os.getenv("HOSAKA_LOCAL_FIRST", "0").strip().lower() in ("1", "true", "yes", "on")
    alias = OLLAMA_DEFAULT_ALIAS if local_first else OPENAI_DEFAULT_MODEL
    if not defaults.get("model_name"):
        defaults["model_name"] = alias
    defaults["max_tokens"] = 4096
    defaults.setdefault("max_tool_iterations", 50)

    model_list = config.setdefault("model_list", [])
    if isinstance(model_list, list):
        if not any(
            isinstance(entry, dict) and entry.get("model_name") == alias
            for entry in model_list
        ):
            model_list.insert(0, {
                "model_name": alias,
                "model": f"ollama/{OLLAMA_DEFAULT_MODEL}" if local_first else f"openai/{OPENAI_DEFAULT_MODEL}",
                "api_base": OLLAMA_DEFAULT_BASE_URL if local_first else "https://api.openai.com/v1",
            })

    gateway = config.setdefault("gateway", {})
    gateway.setdefault("host", "127.0.0.1")
    gateway.setdefault("port", 18790)

    tools = config.setdefault("tools", {})
    read_paths = tools.get("allow_read_paths")
    if not isinstance(read_paths, list):
        read_paths = []
    tools["allow_read_paths"] = read_paths
    if "/" not in read_paths:
        read_paths.append("/")
    write_paths = tools.get("allow_write_paths")
    if not isinstance(write_paths, list):
        write_paths = []
    tools["allow_write_paths"] = write_paths
    for candidate in (str(home_path), "/tmp"):
        if candidate not in write_paths:
            write_paths.append(candidate)

    tools.setdefault("find_skills", {}).setdefault("enabled", True)
    tools.setdefault("install_skill", {}).setdefault("enabled", True)
    tools.setdefault("web", {})["prefer_native"] = False
    skills_cfg = tools.setdefault("skills", {})
    skills_cfg.setdefault("enabled", True)
    registries = skills_cfg.setdefault("registries", {})
    clawhub = registries.setdefault("clawhub", {})
    clawhub.setdefault("enabled", True)
    clawhub.setdefault("base_url", "https://clawhub.ai")
    clawhub.setdefault("search_path", "")
    clawhub.setdefault("skills_path", "")
    clawhub.setdefault("download_path", "")

    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def configure_appliance_runtime(user: str) -> None:
    import pwd

    if os.geteuid() != 0:
        raise PermissionError("Appliance runtime configuration requires root.")
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError("Choose a non-root appliance operator.")
    state_dir = Path(os.getenv("HOSAKA_STATE_PATH", "/var/lib/hosaka/state.json")).parent
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chown(state_dir, account.pw_uid, account.pw_gid)
    config_path = state_dir / "llm.json"
    if config_path.exists():
        os.chown(config_path, account.pw_uid, account.pw_gid)
        config_path.chmod(0o600)
    from hosaka.llm import llm_config

    config = llm_config.load()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not config_path.exists() or (
        config.get("provider") == "openai" and not config.get("api_key") and key
    ):
        if config.get("provider") == "openai" and key:
            config["api_key"] = key
        llm_config.save(config)
    subprocess.run(
        ["runuser", "-u", user, "--", sys.executable,
         str(REPO_ROOT / "scripts/bootstrap_picoclaw_runtime.py"),
         "--home", account.pw_dir, "--seed-config"],
        cwd=REPO_ROOT, check=True,
    )
    ensure_picoclaw_runtime(home=pwd.getpwuid(0).pw_dir, seed_config=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PicoClaw runtime files from Hosaka source")
    parser.add_argument("--home", default=os.path.expanduser("~"))
    parser.add_argument("--seed-config", action="store_true")
    parser.add_argument("--appliance-user", help="prepare shared settings and both appliance agent runtimes (root)")
    args = parser.parse_args()
    if args.appliance_user:
        configure_appliance_runtime(args.appliance_user)
    else:
        ensure_picoclaw_runtime(home=args.home, seed_config=args.seed_config)


if __name__ == "__main__":
    main()
