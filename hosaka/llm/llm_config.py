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
OLLAMA_DEFAULT_BASE_URL = "http://100.78.174.79:11434/v1"
OLLAMA_DEFAULT_API_KEY = "ollama"
OLLAMA_DEFAULT_MODEL = "qwen2.5:0.5b"


def openai_compatible_defaults() -> dict[str, str]:
    return {
        "provider": "openai-compatible",
        "model": os.getenv("HOSAKA_OLLAMA_MODEL", OLLAMA_DEFAULT_MODEL),
        "base_url": os.getenv("HOSAKA_OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL),
        "api_key": os.getenv("HOSAKA_OLLAMA_API_KEY", OLLAMA_DEFAULT_API_KEY),
    }


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
        if os.getenv("HOSAKA_LOCAL_FIRST", "1").strip().lower() in ("1", "true", "yes", "on"):
            return openai_compatible_defaults()
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
    if cfg.get("provider") == "openai-compatible":
        defaults = openai_compatible_defaults()
        os.environ["OPENAI_API_KEY"] = str(cfg.get("api_key") or defaults["api_key"])
        os.environ["OPENAI_MODEL"] = str(cfg.get("model") or defaults["model"])
        os.environ["OPENAI_BASE_URL"] = str(cfg.get("base_url") or defaults["base_url"])
        return

    if cfg.get("api_key"):
        os.environ["OPENAI_API_KEY"] = cfg["api_key"]
    if cfg.get("model"):
        os.environ["OPENAI_MODEL"] = cfg["model"]
    if cfg.get("base_url"):
        os.environ["OPENAI_BASE_URL"] = cfg["base_url"]
    elif "OPENAI_BASE_URL" in os.environ and not cfg.get("base_url"):
        # clear a stale override so the default endpoint is used
        os.environ.pop("OPENAI_BASE_URL", None)
