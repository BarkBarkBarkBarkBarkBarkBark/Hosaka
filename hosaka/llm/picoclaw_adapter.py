"""Picoclaw adapter — calls `picoclaw agent` as a subprocess.

Picoclaw (https://github.com/sipeed/picoclaw) is a lightweight local agent.
This adapter drives the `picoclaw agent` CLI directly.

Key facts:
- `picoclaw agent -m "..." --session KEY` sends one message and exits.
- Session key persists conversation history across calls.
- Output: ANSI banner lines + a response line prefixed with "🦞 ".
- Streaming: we yield the response text word-by-word for a streaming feel.
"""

from __future__ import annotations

import os
import json
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator

PICOCLAW_BIN = os.getenv("PICOCLAW_BIN", "picoclaw")
DEFAULT_SESSION = os.getenv("PICOCLAW_SESSION", "hosaka:main")
PICOCLAW_HOME = os.getenv("PICOCLAW_HOME")

_FAIL_MARKERS = (
    "llm call failed after retries",
    "error processing message",
)


def _config_model_name() -> str:
    from hosaka.llm.openai_adapter import _picoclaw_config_path

    path = _picoclaw_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(
            data.get("agents", {}).get("defaults", {}).get("model_name") or ""
        ).strip()
    except Exception:
        return ""


def active_model() -> str:
    return os.getenv("PICOCLAW_MODEL", "") or _config_model_name()


DEFAULT_MODEL = active_model()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
_RESPONSE_PREFIX = "🦞"


def is_available() -> bool:
    return bool(shutil.which(PICOCLAW_BIN))


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _is_banner_line(clean: str) -> bool:
    """Return True if the line is a picoclaw banner/chrome line."""
    return (
        clean.startswith(("█", "╚", "╔", "╠", "╩", "═"))
        or bool(re.match(r"^(?:🦞\s+)?picoclaw\s+\d", clean, re.IGNORECASE))
        or bool(re.match(r"^\d{2}:\d{2}:\d{2}\s+(?:WRN|INF|DBG|ERR)\s", clean))
        or clean.startswith(("Interactive mode", "Goodbye", "Press Ctrl+C"))
    )


def _extract_response(raw_output: str) -> str:
    """Pull the agent response out of picoclaw's decorated output.

    Supports multi-line responses: collects from the first 🦞 line through
    all subsequent non-banner lines.
    """
    all_lines = raw_output.splitlines()

    # Find the first 🦞 response line
    for idx, line in enumerate(all_lines):
        clean = _strip_ansi(line).strip()
        if clean.startswith(_RESPONSE_PREFIX) and not _is_banner_line(clean):
            collected = [clean[len(_RESPONSE_PREFIX):].strip()]
            # Gather continuation lines after the 🦞 prefix
            for cont in all_lines[idx + 1:]:
                c = _strip_ansi(cont).strip()
                if not c or _is_banner_line(c):
                    continue
                collected.append(c)
            return "\n".join(collected)

    # Fallback: return everything that isn't the banner
    lines = [
        _strip_ansi(l).strip()
        for l in all_lines
        if _strip_ansi(l).strip() and not _is_banner_line(_strip_ansi(l).strip())
    ]
    return "\n".join(lines)


def chat_sync(
    message: str,
    session: str | None = None,
    timeout: float = 120,
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    model: str | None = None,
) -> str:
    """Send a message to picoclaw and return the response text."""
    session = session or DEFAULT_SESSION
    cmd = [PICOCLAW_BIN, "agent", "-m", message, "--session", session]
    model = active_model() if model is None else model
    if model:
        cmd += ["--model", model]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env if env is not None else {
                **os.environ,
                **({"PICOCLAW_HOME": PICOCLAW_HOME} if PICOCLAW_HOME else {}),
            },
        )
        output = result.stdout + result.stderr
        if result.returncode != 0 or any(marker in output.lower() for marker in _FAIL_MARKERS):
            raise RuntimeError(
                _strip_ansi(result.stderr).strip()
                or f"picoclaw exited with status {result.returncode}: {_extract_response(result.stdout)}"
            )
        text = _extract_response(result.stdout)
        if not text:
            raise RuntimeError("picoclaw returned an empty response")
        return text
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("picoclaw timed out") from exc


def chat_stream(message: str, session: str | None = None) -> Generator[str, None, None]:
    """Send a message and yield response tokens (word-by-word streaming)."""
    response = chat_sync(message, session=session)
    yield from _response_tokens(response)


def _response_tokens(response: str) -> Generator[str, None, None]:
    # Yield word by word, preserving newlines for multi-line responses
    for line_idx, line in enumerate(response.split("\n")):
        if line_idx > 0:
            yield "\n"
        words = line.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")


def console_chat_stream(
    messages: list[dict[str, str]],
    session: str | None = None,
    cwd: str | None = None,
    timeout: float = 120,
) -> Generator[str, None, None]:
    """Use Hosaka's selected model inside PicoClaw, never direct completions.

    A private, temporary config overlay preserves the original workspace,
    native tool policy, and session storage without changing other agents.
    """
    from hosaka.llm import openai_adapter

    if not is_available():
        raise RuntimeError("PicoClaw is not installed. Install picoclaw before using /llm.")
    config_path = openai_adapter._picoclaw_config_path()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot load PicoClaw config at {config_path}. Run picoclaw onboard.") from exc
    if not isinstance(config, dict) or not isinstance(config.get("model_list"), list):
        raise RuntimeError("PicoClaw config must contain a model_list.")
    agents = config.get("agents")
    defaults = agents.get("defaults") if isinstance(agents, dict) else None
    if not isinstance(defaults, dict):
        raise RuntimeError("PicoClaw config must contain agents.defaults.")
    workspace = Path(str(defaults.get("workspace") or config_path.parent / "workspace")).expanduser()
    if not workspace.is_absolute():
        workspace = config_path.parent / workspace
    override = os.getenv("HOSAKA_WORKSPACE")
    if override:
        workspace = Path(override).expanduser().resolve()
        if not workspace.is_dir():
            raise RuntimeError(f"Hosaka workspace does not exist: {workspace}")
    defaults["workspace"] = str(workspace)
    user_message = next(
        (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"),
        "",
    )
    if not user_message.strip():
        raise ValueError("PicoClaw chat requires a user message.")
    context = "\n\n".join(
        msg.get("content", "") for msg in messages if msg.get("role") == "system"
    )
    project = os.getenv("HOSAKA_PROJECT_DIR")
    if project:
        project_path = Path(project).expanduser().resolve()
        if not project_path.is_dir():
            raise RuntimeError(f"Hosaka project directory does not exist: {project_path}")
        context += (
            f"\n\nOperator project directory: {project_path}. Use this absolute path for project "
            "files and set command working directories there. Your configured agent workspace "
            "is private runtime storage for identity, memory, and sessions, not the operator project. "
            "The project mount may be read-only; report permission errors rather than bypassing them."
        )
    message = f"{context}\n\nOperator request:\n{user_message}" if context else user_message

    model = os.getenv("PICOCLAW_MODEL", "").strip()
    security_path = openai_adapter._picoclaw_security_path()
    security_text = security_path.read_text(encoding="utf-8") if security_path.exists() else ""
    if not model:
        key = openai_adapter._api_key()
        if not key and openai_adapter._base_url() == "https://api.openai.com":
            raise RuntimeError("No model credential configured. Use /select llm or configure an API key.")
        model = "hosaka-console"
        config["model_list"] = [
            entry for entry in config["model_list"]
            if not isinstance(entry, dict) or entry.get("model_name") != model
        ]
        config["model_list"].append({
            "model_name": model,
            "model": f"openai/{openai_adapter._model()}",
            "api_base": openai_adapter._api_base_url(),
        })
        if config.get("version", 0) >= 3:
            if re.search(r"^  hosaka-console:\d+:", security_text, re.MULTILINE):
                raise RuntimeError("PicoClaw security config already uses the reserved hosaka-console alias.")
            entry = f"  hosaka-console:0:\n    api_keys:\n      - {json.dumps(key or '')}\n"
            header = re.search(r"^model_list:[ \t]*\n", security_text, re.MULTILINE)
            if header:
                security_text = security_text[:header.end()] + entry + security_text[header.end():]
            elif re.search(r"^model_list:", security_text, re.MULTILINE):
                raise RuntimeError("PicoClaw security model_list must be a block mapping.")
            else:
                security_text += "\nmodel_list:\n" + entry
        else:
            config["model_list"][-1]["api_key"] = key or ""

    with tempfile.TemporaryDirectory(prefix="hosaka-picoclaw-") as directory:
        runtime = Path(directory)
        private_config = runtime / "config.json"
        private_config.touch(mode=0o600)
        private_config.write_text(json.dumps(config), encoding="utf-8")
        if security_text:
            private_security = runtime / ".security.yml"
            private_security.touch(mode=0o600)
            private_security.write_text(security_text, encoding="utf-8")
        env = {**os.environ, "PICOCLAW_HOME": str(runtime)}
        env.pop("PICOCLAW_CONFIG_PATH", None)
        response = chat_sync(
            message, session=_console_session_key(session or "hosaka:tui"), timeout=timeout,
            cwd=cwd, env=env, model=model,
        )
        yield from _response_tokens(response)


def _console_session_key(alias: str) -> str:
    # PicoClaw 0.2.x routes ordinary CLI aliases to the shared main session.
    if alias.startswith(("sk_v1_", "agent:")):
        return alias
    return "sk_v1_" + hashlib.sha256(alias.strip().lower().encode("utf-8")).hexdigest()
