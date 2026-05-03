"""OpenAI API adapter — fallback when picoclaw / gateway is unavailable."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Generator

import httpx

_OPENAI_DEFAULT_BASE = "https://api.openai.com"
REQUEST_TIMEOUT = float(os.getenv("HOSAKA_CHAT_TIMEOUT", "120"))
TRANSCRIBE_TIMEOUT = float(os.getenv("HOSAKA_TRANSCRIBE_TIMEOUT", "120"))


def _base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", _OPENAI_DEFAULT_BASE).rstrip("/")


def _chat_url() -> str:
    return f"{_base_url()}/v1/chat/completions"


def _transcriptions_url() -> str:
    return f"{_base_url()}/v1/audio/transcriptions"


def _picoclaw_config_path() -> Path:
    raw = os.getenv("PICOCLAW_CONFIG_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".picoclaw" / "config.json"


def _picoclaw_security_path() -> Path:
    raw = os.getenv("PICOCLAW_SECURITY_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _picoclaw_config_path().parent / ".security.yml"


def _load_picoclaw_config() -> dict:
    try:
        return json.loads(_picoclaw_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _preferred_picoclaw_model(cfg: dict) -> str:
    default_model = ""
    if isinstance(cfg, dict):
        agents = cfg.get("agents")
        if isinstance(agents, dict):
            defaults = agents.get("defaults")
            if isinstance(defaults, dict):
                default_model = str(defaults.get("model_name") or "").strip()
    return os.getenv("PICOCLAW_MODEL", "").strip() or default_model


def _picoclaw_api_key(cfg: dict) -> str | None:
    model_list = cfg.get("model_list")
    if not isinstance(model_list, list):
        return None

    preferred = _preferred_picoclaw_model(cfg)

    def _entry_key(entry: object) -> str | None:
        if not isinstance(entry, dict):
            return None
        key = str(entry.get("api_key") or "").strip()
        return key or None

    if preferred:
        for entry in model_list:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("model_name") or "").strip() == preferred:
                key = _entry_key(entry)
                if key:
                    return key

    for entry in model_list:
        key = _entry_key(entry)
        if key:
            return key
    return None


def _load_picoclaw_security() -> dict:
    """Read ~/.picoclaw/.security.yml — picoclaw stores per-model API keys here."""
    path = _picoclaw_security_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return _parse_security_yaml_fallback(raw)
    try:
        data = yaml.safe_load(raw)
    except Exception:
        return _parse_security_yaml_fallback(raw)
    return data if isinstance(data, dict) else {}


def _parse_security_yaml_fallback(raw: str) -> dict:
    """Minimal YAML parser for the .security.yml shape we care about.

    Only handles ``model_list: <name>:N:\\n  api_keys:\\n    - <key>`` so we
    can still resolve the key even when PyYAML isn't installed (the voice
    daemon and webserver venvs may be lean).
    """
    out: dict[str, dict] = {"model_list": {}}
    model_list = out["model_list"]
    current_entry: dict | None = None
    in_api_keys = False
    in_model_list = False
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.rstrip()
        if not stripped.startswith(" ") and not stripped.startswith("\t"):
            in_model_list = stripped.startswith("model_list:")
            current_entry = None
            in_api_keys = False
            continue
        if not in_model_list:
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        body = stripped.strip()
        if indent == 2 and body.endswith(":"):
            name = body[:-1].strip()
            current_entry = {"api_keys": []}
            model_list[name] = current_entry
            in_api_keys = False
            continue
        if current_entry is None:
            continue
        if indent == 4 and body == "api_keys:":
            in_api_keys = True
            continue
        if in_api_keys and body.startswith("- "):
            value = body[2:].strip().strip("'\"")
            if value:
                current_entry.setdefault("api_keys", []).append(value)
            continue
        if indent == 4:
            in_api_keys = False
    return out


def _picoclaw_security_api_key(cfg: dict, security: dict) -> str | None:
    model_list = security.get("model_list")
    if not isinstance(model_list, dict):
        return None

    preferred = _preferred_picoclaw_model(cfg)

    def _entry_key(entry: object) -> str | None:
        if not isinstance(entry, dict):
            return None
        keys = entry.get("api_keys")
        if isinstance(keys, list):
            for candidate in keys:
                value = str(candidate or "").strip()
                if value:
                    return value
        single = str(entry.get("api_key") or "").strip()
        return single or None

    if preferred:
        for name, entry in model_list.items():
            base = str(name).split(":", 1)[0].strip()
            if base == preferred:
                key = _entry_key(entry)
                if key:
                    return key

    for entry in model_list.values():
        key = _entry_key(entry)
        if key:
            return key
    return None


def resolve_api_key() -> tuple[str | None, str | None]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key, "env"

    try:
        from hosaka.llm import llm_config

        cfg = llm_config.load()
    except Exception:
        cfg = {}
    key = str(cfg.get("api_key") or "").strip() if isinstance(cfg, dict) else ""
    if key:
        return key, "llm.json"

    pico_cfg = _load_picoclaw_config()
    key = _picoclaw_api_key(pico_cfg) or ""
    if key:
        return key, "~/.picoclaw/config.json"

    key = _picoclaw_security_api_key(pico_cfg, _load_picoclaw_security()) or ""
    if key:
        return key, "~/.picoclaw/.security.yml"

    return None, None


def _api_key() -> str | None:
    key, _source = resolve_api_key()
    return key


def _model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def is_available() -> bool:
    """Return True if OPENAI_API_KEY is set."""
    return bool(_api_key())


def chat_stream(messages: list[dict[str, str]]) -> Generator[str, None, None]:
    """Stream chat completion tokens from OpenAI."""
    key = _api_key()
    if not key:
        yield "OPENAI_API_KEY is not set."
        return
    payload = {
        "model": _model(),
        "messages": messages,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        with client.stream("POST", _chat_url(), json=payload, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def chat_sync(messages: list[dict[str, str]]) -> str:
    """Non-streaming chat completion from OpenAI."""
    key = _api_key()
    if not key:
        return "OPENAI_API_KEY is not set."
    payload = {
        "model": _model(),
        "messages": messages,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.post(_chat_url(), json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    filename: str = "voice.webm",
    content_type: str = "audio/webm",
    model: str | None = None,
    prompt: str | None = None,
    language: str | None = None,
) -> str:
    """Run OpenAI audio transcription over raw uploaded audio bytes."""
    key = _api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    data: dict[str, str] = {
        "model": (model or os.getenv("HOSAKA_VOICE_TRANSCRIBE_MODEL", "whisper-1")).strip() or "whisper-1",
        "response_format": "json",
    }
    if prompt:
        data["prompt"] = prompt
    if language:
        data["language"] = language

    # OpenAI Whisper only accepts bare media types without codec parameters.
    # Strip anything after the first semicolon (e.g. "audio/webm;codecs=opus" → "audio/webm").
    bare_type = (content_type or "audio/webm").split(";")[0].strip().lower()

    # Map the media type to an extension Whisper accepts.  If the caller
    # already gave a well-formed filename we keep it; otherwise we derive one.
    _MIME_TO_EXT: dict[str, str] = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
        "audio/mpga": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
        "video/webm": "webm",
        "video/mp4": "mp4",
    }
    ext = _MIME_TO_EXT.get(bare_type, "webm")
    # Ensure the filename has a matching extension so Whisper can sniff the format.
    import posixpath
    base, _, old_ext = filename.rpartition(".")
    if old_ext.lower() not in _MIME_TO_EXT.values():
        filename = f"{filename}.{ext}" if not base else f"{base}.{ext}"

    files = {
        "file": (filename, audio_bytes, bare_type),
    }
    headers = {"Authorization": f"Bearer {key}"}

    async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT) as client:
        resp = await client.post(_transcriptions_url(), data=data, files=files, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        return str(payload.get("text") or "").strip()
