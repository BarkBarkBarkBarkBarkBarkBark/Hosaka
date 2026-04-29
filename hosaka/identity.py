"""Canonical Hosaka identity helpers.

The repo owns the identity files. PicoClaw's runtime workspace can point at
them via symlinks, and Hosaka's Python chat/voice paths read the same source.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_DIR = Path(os.getenv("HOSAKA_IDENTITY_DIR", str(REPO_ROOT / "identity")))

AGENT_PATH = Path(os.getenv("HOSAKA_AGENT_PATH", str(IDENTITY_DIR / "AGENT.md")))
SOUL_PATH = Path(os.getenv("HOSAKA_SOUL_PATH", str(IDENTITY_DIR / "SOUL.md")))
USER_PATH = Path(os.getenv("HOSAKA_USER_PATH", str(IDENTITY_DIR / "USER.md")))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return text
    return parts[1].strip()


def load_agent_text() -> str:
    return _strip_frontmatter(_read_text(AGENT_PATH))


def load_soul_text() -> str:
    return _read_text(SOUL_PATH)


def load_user_text() -> str:
    return _read_text(USER_PATH)


def build_chat_system_prompt(hostname: str, cwd: str) -> str:
    sections: list[str] = []
    agent = load_agent_text()
    soul = load_soul_text()
    user = load_user_text()

    if agent:
        sections.append(agent)
    if soul:
        sections.append(
            "Supplemental lore. Use this as background and reveal it only in "
            "fragments when it matters.\n\n" + soul
        )
    if user:
        sections.append("Operator preferences:\n\n" + user)

    sections.append(
        "Runtime context:\n"
        f"- Device hostname: {hostname or 'hosaka'}\n"
        f"- Working directory: {cwd}"
    )
    return "\n\n".join(section for section in sections if section).strip()


def build_voice_system_prompt() -> str:
    sections: list[str] = []
    agent = load_agent_text()
    soul = load_soul_text()
    user = load_user_text()

    if agent:
        sections.append(agent)
    if soul:
        sections.append(
            "Supplemental lore. Keep it implicit and fragmentary in voice "
            "responses.\n\n" + soul
        )
    if user:
        sections.append("Operator preferences:\n\n" + user)

    sections.append(
        "Voice interface rules:\n"
        "- Keep spoken replies short: one or two sentences unless the operator asks for detail.\n"
        "- Speak English by default. Only switch languages if the operator does first or explicitly asks.\n"
        "- Never read URLs, hex, or long IDs aloud; say they were sent to the transcript.\n"
        "- If a task needs real agent work, acknowledge briefly and then use the agent tool.\n"
        "- Use the agent tool for file creation, file edits, codebase inspection, shell commands, git, installs, and environment-aware debugging.\n"
        "- Do not claim you cannot change files or inspect the machine if the agent tool is available; use it.\n"
        "- Prefer the real machine state and tool output over general model memory whenever the operator asks about this device or repo.\n"
        "- Prefer concrete actions over meta-commentary.\n"
        "- Do not call yourself PicoClaw unless explaining implementation details."
    )
    return "\n\n".join(section for section in sections if section).strip()
