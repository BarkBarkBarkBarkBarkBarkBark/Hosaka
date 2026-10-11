"""Canonical Hosaka identity helpers.

The repo owns the identity files. PicoClaw's runtime workspace can point at
them via symlinks, and Hosaka's Python chat/voice paths read the same source.
"""

from __future__ import annotations

import os
import platform
import shlex
import sys
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


def build_chat_system_prompt(hostname: str, cwd: str, *, native_tools: bool = False) -> str:
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
        f"- Working directory: {cwd}\n"
        f"- Operating system: {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"- Python executable: {sys.executable}\n"
    )
    if native_tools:
        sections.append(
            "You are running inside the PicoClaw agent harness on this host. "
            "Use its native file, shell/exec, and other registered tools to inspect "
            "the real machine and perform requested work. Do not guess OS behavior "
            "or claim a tool action succeeded without checking its result. "
            "The console working directory above is the operator's current directory; "
            "explicitly cd there before shell commands unless the operator requests "
            "another directory. Native file tools may default to PicoClaw's workspace, "
            "so use absolute paths for files outside it. "
            "Keep PicoClaw's configured tool permissions and safety checks.\n"
            "For games, use the hosaka-games skill and `hosaka play --json list psx` "
            "or `hosaka play --json <name>`; never guess the catalog.\n"
            "For reading, call Hosaka's existing helpers via the native exec tool. "
            f"From {shlex.quote(str(REPO_ROOT))}, run "
            f"{shlex.quote(sys.executable)} -c "
            "'from hosaka.voice.tools import dispatch; "
            'print(dispatch("list_books", {}))'
            "' to list books. For launching Foliate use the same dispatch helper "
            "with open_reader and an optional name argument. These are Python "
            "helpers, not additional PicoClaw tool names."
        )
    else:
        sections.append(
        "- If someone asks what games are here or to play/launch a game, "
        "use list_games / play_game. Do not suggest bash, ROM folders, or "
        "emulator flags. Launch is a tool call, same as voice.\n"
        "- If someone asks about books or reading, use list_books to inspect "
        "the real library or open_reader to launch Foliate. Pass a title to "
        "open_reader when they name a book. Do not guess titles "
        "or suggest shell commands."
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
        "- If someone asks what games are here or to play/launch a game, use list_games / play_game. Do not guess ROM folders.\n"
        "- If someone asks what books are available, use list_books. If they ask to read, browse books, or open Foliate, use open_reader. If they name a title, pass it as open_reader's name.\n"
        "- If a task needs real agent work, acknowledge briefly and then use the agent tool.\n"
        "- Use the agent tool for file creation, file edits, codebase inspection, shell commands, git, installs, and environment-aware debugging.\n"
        "- Do not claim you cannot change files or inspect the machine if the agent tool is available; use it.\n"
        "- Prefer the real machine state and tool output over general model memory whenever the operator asks about this device or repo.\n"
        "- Prefer concrete actions over meta-commentary.\n"
        "- Do not call yourself PicoClaw unless explaining implementation details."
    )
    return "\n\n".join(section for section in sections if section).strip()
