"""Persistent LLM provider configuration.

Stored in the same directory as state.json so it survives container restarts
when the state volume is mounted.  The file contains the api key — never log
or expose its contents via API responses.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

_STATE_PATH_ENV = "HOSAKA_STATE_PATH"
_SYSTEM_DIR = Path("/var/lib/hosaka")
_USER_DIR = Path.home() / ".hosaka"
OLLAMA_DEFAULT_BASE_URL = "http://100.78.174.79:11434/v1"
OLLAMA_DEFAULT_API_KEY = "ollama"
OLLAMA_DEFAULT_MODEL = "qwen2.5:0.5b"
OLLAMA_DISCOVERY_URLS = "http://127.0.0.1:11434,http://100.78.174.79:11434"
OPENAI_DEFAULT_MODEL = "gpt-4.1"


def openai_compatible_defaults() -> dict[str, str]:
    return {
        "provider": "openai-compatible",
        "model": os.getenv("HOSAKA_OLLAMA_MODEL", OLLAMA_DEFAULT_MODEL),
        "base_url": os.getenv("HOSAKA_OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL),
        "api_key": os.getenv("HOSAKA_OLLAMA_API_KEY", OLLAMA_DEFAULT_API_KEY),
    }


def ollama_discovery_urls() -> list[str]:
    """Return operator-configured Ollama hosts without scanning a subnet."""
    raw = os.getenv("HOSAKA_OLLAMA_DISCOVERY_URLS", OLLAMA_DISCOVERY_URLS)
    return [url.strip().rstrip("/") for url in raw.split(",") if url.strip()]


def discover_ollama(
    candidates: Iterable[str] | None = None,
    *,
    timeout: float = 1.5,
) -> dict | None:
    """Find the first configured Ollama host that serves ``/api/tags``."""
    for candidate in candidates or ollama_discovery_urls():
        base_url = str(candidate).strip().rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        if not base_url.startswith(("http://", "https://")):
            continue
        try:
            with urlopen(f"{base_url}/api/tags", timeout=timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            continue
        models = [
            str(item.get("name") or item.get("model") or "").strip()
            for item in payload.get("models", [])
            if isinstance(item, dict)
        ]
        models = [model for model in models if model]
        if models:
            return {"base_url": base_url, "models": models}
    return None


def require_ollama(base_url: str, model: str) -> dict:
    """Check the selected host/model before sending a completion request."""
    result = discover_ollama([base_url], timeout=1.0)
    if not result:
        raise RuntimeError(
            f"Ollama is unavailable at {base_url}. No chat request was sent. "
            "Start Ollama or use /select llm to choose another provider."
        )
    if model not in result["models"]:
        raise RuntimeError(
            f"Ollama model {model!r} is not installed at {base_url}. "
            "Use /select llm to choose an installed model."
        )
    return result


def discovered_ollama_config(current: dict | None = None) -> dict | None:
    """Build a persistable OpenAI-compatible configuration from a live host."""
    result = discover_ollama()
    if not result:
        return None
    current = current or {}
    models = result["models"]
    preferred = str(current.get("model") or "").strip()
    if preferred not in models:
        preferred = os.getenv("HOSAKA_OLLAMA_MODEL", OLLAMA_DEFAULT_MODEL)
    model = preferred if preferred in models else models[0]
    return replace_active_config(current, {
        "provider": "openai-compatible",
        "base_url": f"{result['base_url']}/v1",
        "api_key": OLLAMA_DEFAULT_API_KEY,
        "model": model,
        "ollama_discovery": True,
        "ollama_models": models,
    })


def replace_active_config(current: dict | None, replacement: dict) -> dict:
    """Replace active settings while retaining named provider profiles."""
    current = current or {}
    profiles = current.get("profiles")
    profiles = dict(profiles) if isinstance(profiles, dict) else {}
    provider = str(current.get("provider") or "")
    if provider == "openai":
        profiles["openai"] = {key: value for key, value in current.items() if key != "profiles"}
    elif provider == "openai-compatible":
        profiles["ollama"] = {key: value for key, value in current.items() if key != "profiles"}
    result = dict(replacement)
    result["profiles"] = profiles
    return result


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
        if os.getenv("HOSAKA_LOCAL_FIRST", "0").strip().lower() in ("1", "true", "yes", "on"):
            return openai_compatible_defaults()
        return {
            "provider": "openai",
            "model": OPENAI_DEFAULT_MODEL,
            "base_url": "https://api.openai.com",
        }


def save(cfg: dict) -> None:
    f = _config_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".llm-", dir=f.parent, delete=False,
        ) as temporary:
            path = Path(temporary.name)
            try:
                if os.name == "posix" and os.geteuid() == 0:
                    owner = f.parent.stat()
                    os.fchown(temporary.fileno(), owner.st_uid, owner.st_gid)
                temporary.write(json.dumps(cfg, indent=2))
                temporary.flush()
                os.fsync(temporary.fileno())
                os.replace(path, f)
            finally:
                path.unlink(missing_ok=True)
    except OSError as exc:
        import logging
        logging.getLogger("hosaka.llm.llm_config").warning("could not save llm config: %s", exc)
        raise


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
