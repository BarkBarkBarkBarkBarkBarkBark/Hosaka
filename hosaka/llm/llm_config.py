"""Persistent LLM provider configuration.

Stored in the same directory as state.json so it survives container restarts
when the state volume is mounted.  The file contains the api key — never log
or expose its contents via API responses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_STATE_PATH_ENV = "HOSAKA_STATE_PATH"
_SYSTEM_DIR = Path("/var/lib/hosaka")
_USER_DIR = Path.home() / ".hosaka"


def _config_dir() -> Path:
    state_path = os.getenv(_STATE_PATH_ENV)
    if state_path:
        return Path(state_path).parent
    if _SYSTEM_DIR.exists():
        return _SYSTEM_DIR
    return _USER_DIR


def _config_file() -> Path:
    return _config_dir() / "llm.json"


def load() -> dict:
    try:
        return json.loads(_config_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(cfg: dict) -> None:
    f = _config_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError as exc:
        import logging
        logging.getLogger("hosaka.llm.llm_config").warning("could not save llm config: %s", exc)


def apply_to_env(cfg: dict) -> None:
    """Inject stored values into os.environ so openai_adapter picks them up."""
    if cfg.get("api_key"):
        os.environ["OPENAI_API_KEY"] = cfg["api_key"]
    if cfg.get("model"):
        os.environ["OPENAI_MODEL"] = cfg["model"]
    if cfg.get("base_url"):
        os.environ["OPENAI_BASE_URL"] = cfg["base_url"]
    elif "OPENAI_BASE_URL" in os.environ and not cfg.get("base_url"):
        # clear a stale override so the default endpoint is used
        os.environ.pop("OPENAI_BASE_URL", None)
