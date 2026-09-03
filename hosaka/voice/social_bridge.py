"""TUI-only SocialEngine adapter for the existing voice daemon.

Realtime remains ASR + TTS. SocialEngine decides whether Hosaka may speak.
The ASCII orb and HOLD/SPEAK line print to the terminal; the web GUI is
untouched.

This module imports ``hosaka_social`` only when the package is installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import deque
from typing import Any

log = logging.getLogger("hosaka.voice.social")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_ORB_INTENSITY = {
    "idle": 0,
    "sleeping": 0,
    "listening": 1,
    "thinking": 1,
    "chambered": 2,
    "confused": 2,
    "speaking": 3,
    "excited": 3,
    "interrupted": 1,
}


def social_available() -> bool:
    try:
        import hosaka_social  # noqa: F401
    except ImportError:
        return False
    return True


def social_enabled() -> bool:
    raw = os.getenv("HOSAKA_SOCIAL_COGNITION", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"} and social_available()


def chatty_enabled() -> bool:
    """Talk back on every turn. Default off — only answer when asked."""
    raw = os.getenv("HOSAKA_VOICE_CHATTY", "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def voice_debug_enabled() -> bool:
    raw = os.getenv("HOSAKA_VOICE_DEBUG", "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


_TOOL_HINTS = {
    "see": "looking around…",
    "ask_agent": "thinking it through…",
    "play_game": "launching a game…",
    "list_games": "checking the library…",
    "list_books": "checking the shelf…",
    "open_reader": "opening the reader…",
    "todo_add": "adding a todo…",
    "get_status": "checking status…",
    "set_mode": "switching modes…",
    "write_doc": "writing a note…",
    "append_doc": "updating a note…",
    "write_doc_template": "writing a note…",
    "list_docs": "looking through notes…",
    "read_doc": "reading a note…",
}


def tool_hint(name: str, detail: str = "") -> str:
    token = (name or "").strip().lower().replace("tool ", "")
    rest = (detail or "").strip()
    if token == "play_game" and rest:
        return f"launching {rest}…"
    if token == "open_reader" and rest:
        return f"opening {rest}…"
    return _TOOL_HINTS.get(token, "working on it…")


_DIRECT_RE = re.compile(
    r"\b("
    r"hosaka|launch|lunch|lounge|play|start|stop|quit|open|"
    r"what|why|how|when|where|who|which|"
    r"can you|could you|would you|please|"
    r"tony hawk|thps|crash|spyro|spiral|"
    r"read|book|books|ebook|ebooks|foliate|foliage|reader"
    r")\b|[?]",
    re.I,
)

_ASR_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blunch\b", re.I), "launch"),
    (re.compile(r"\blounge\b", re.I), "launch"),
    (re.compile(r"\b(launch|play|start)\s+fire\b", re.I), r"\1 spyro"),
    (re.compile(r"\bspiral\b", re.I), "spyro"),
    (re.compile(r"\bspiro\b", re.I), "spyro"),
    (re.compile(r"\bspero\b", re.I), "spyro"),
    (re.compile(r"\bsparrow\b", re.I), "spyro"),
    (re.compile(r"\bthps\b", re.I), "tony hawk"),
    (re.compile(r"\bfoliage\b", re.I), "foliate"),
)

_READ_NAME_SKIP = frozenset(
    {
        "foliate",
        "foliage",
        "reader",
        "book",
        "books",
        "ebook",
        "ebooks",
        "library",
        "shelf",
        "something",
        "me",
        "it",
        "that",
        "this",
        "some",
        "any",
    }
)

_LIST_BOOKS_RE = re.compile(
    r"("
    r"\b(what|which|any|how many)\b.{0,40}\b(book|books|ebooks?|reading)\b|"
    r"\b(book|books|ebooks?)\b.{0,24}\b(available|have|here|on (the )?(shelf|terminal))|"
    r"\blist (the )?(books|ebooks?|shelf|library)\b"
    r")",
    re.I,
)

_OPEN_SHELF_RE = re.compile(
    r"("
    r"\b(open|launch|start|show)\b.{0,24}\b(foliate|foliage|reader|bookshelf)\b|"
    r"\b(browse|show|open)\b.{0,16}\b(books|library|shelf)\b|"
    r"\bopen (the )?(book|books|reader|library)\b|"
    r"\b(i want to|let me|lets|let's|wanna)\s+read\b|"
    r"\bread (something|a book|books)\b"
    r")",
    re.I,
)


def repair_transcript(text: str) -> str:
    """Fix common ASR misses for launch-game commands."""
    out = " ".join((text or "").replace(",", " ").split())
    for pattern, repl in _ASR_FIXES:
        out = pattern.sub(repl, out)
    return out


def parse_play_command(text: str) -> str | None:
    if parse_read_command(text) is not None:
        return None
    cleaned = repair_transcript(text).lower()
    if not re.search(r"\b(launch|play|start)\b", cleaned):
        return None
    rest = re.sub(r"\b(please|can you|could you|would you)\b", " ", cleaned)
    rest = re.sub(r"\b(launch|play|start)\b", " ", rest)
    rest = re.sub(r"\b(the|game|a|an)\b", " ", rest)
    name = " ".join(rest.split())
    if not name:
        return None
    if name in _READ_NAME_SKIP or any(token in _READ_NAME_SKIP for token in name.split()):
        return None
    return name


def parse_read_command(text: str) -> dict[str, str] | None:
    cleaned = repair_transcript(text).lower()
    cleaned = re.sub(r"\b(please|can you|could you|would you)\b", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    if _LIST_BOOKS_RE.search(cleaned):
        return {"action": "list"}
    if _OPEN_SHELF_RE.search(cleaned) or cleaned in {"read", "foliate", "open foliate"}:
        return {"action": "open"}
    match = re.search(r"\b(read|open)\b (.+)$", cleaned)
    if match:
        rest = re.sub(
            r"\b(the|a|an|book|ebook|please|in foliate|with foliate)\b",
            " ",
            match.group(2),
        )
        rest = " ".join(rest.split())
        if rest and rest not in _READ_NAME_SKIP:
            return {"action": "open", "name": rest}
    return None


def looks_directed(text: str) -> bool:
    stripped = repair_transcript(text)
    if len(stripped) < 4:
        return False
    return (
        bool(_DIRECT_RE.search(stripped))
        or parse_play_command(stripped) is not None
        or parse_read_command(stripped) is not None
    )


def render_social_status(
    face_state: str,
    decision: str,
    chamber: str,
    *,
    score: float | None = None,
) -> str:
    intensity = _ORB_INTENSITY.get(face_state, 0)
    glyph = "░▒▓█"[max(0, min(3, intensity))]
    score_s = f" {score:.2f}" if score is not None else ""
    snippet = (chamber or "").replace("\n", " ")[:42]
    return f"  {glyph} {face_state:<12} {decision:<10}{score_s:<5} {snippet}"


HUD_ROWS = 18  # blank + 11 orb + wave + status + rt + you + rule
HUD_ROWS_COMPACT = 7


def _term_size() -> tuple[int, int]:
    import shutil

    size = shutil.get_terminal_size(fallback=(80, 24))
    return max(40, size.columns), max(20, size.lines)


def _style(name: str) -> str:
    try:
        from hosaka.tui import style as s
    except Exception:  # noqa: BLE001
        return ""
    return {
        "you": s.GRAY,
        "agent": s.CYAN,
        "meta": s.DARK_GRAY,
        "tool": s.AMBER,
        "text": s.WHITE,
        "agent_text": s.CYAN_DIM,
        "reset": s.R,
        "rule": s.DARK_GRAY,
    }.get(name, "")


def _label(kind: str, text: str) -> str:
    names = {"you": "you", "agent": "hosaka", "tool": "tool", "meta": "·"}
    name = names.get(kind, kind)
    color = _style(kind)
    body = _style("agent_text" if kind == "agent" else "text" if kind in {"you", "tool"} else "meta")
    reset = _style("reset")
    return f"  {color}{name:<7}{reset}{body}{text}{reset}"


class TuiOrbFace:
    """Orb pinned at the top; transcript scrolls underneath (DECSTBM)."""

    def __init__(self, *, stream: Any | None = None, live_log: bool = False) -> None:
        self.states: list[str] = []
        out = stream if stream is not None else sys.__stdout__
        self._stream = out
        self._tty = bool(getattr(out, "isatty", lambda: False)())
        if not self._tty and stream is None:
            self._tty = bool(getattr(sys.__stdout__, "isatty", lambda: False)())
            self._stream = sys.__stdout__
        self._live_log = live_log
        self._split = False
        self._compact = False
        self._hud_rows = HUD_ROWS
        self._rows = 24
        self._state = "idle"
        self._decision = "—"
        self._score: float | None = None
        self._chamber = ""
        self._user = ""
        self._agent = ""
        self._height = 0
        self._last_block = ""
        self._last_hud = ""
        self._spin = 0.0
        self._busy = False
        self._energy = 0.0
        self._rms = 0.0
        self._levels: deque[float] = deque([0.0] * 48, maxlen=48)
        self._rt = ""
        self._tool = ""
        self._last_paint = 0.0
        self._busy_since = 0.0
        self._floor_energy = 0.0

    def _show_hud(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_paint < 0.06:
            return
        self._last_paint = now
        if self._live_log:
            self._enter_split()
            if self._split:
                self._paint_hud()
                return
        self._redraw()

    def set_waiting(self, wakeword: str) -> None:
        self._busy = False
        self._state = "idle"
        self._decision = "WAIT"
        token = wakeword.strip().lower().replace("-", "_")
        if token in {"passthrough", "speak", "off", "none", ""}:
            self._chamber = "listening — esc/q to leave"
        else:
            self._chamber = f"say {wakeword.replace('_', ' ')}  ·  esc/q"
        self._show_hud()

    def note_user(self, text: str) -> None:
        self._user = text.strip()
        if self._live_log:
            if self._agent:
                self._stream.write("\n")
                self._agent = ""
            self._emit(_label("you", self._user))
            return
        self._redraw()

    def note_partial(self, text: str) -> None:
        """Update the HUD you-line without emitting a new transcript row."""
        self._user = text.strip()
        self._show_hud()

    def note_hearing(self) -> None:
        self._busy = False
        self._state = "listening"
        self._decision = "HEAR"
        self._chamber = "hearing you"
        self._show_hud()

    def note_agent(self, text: str) -> None:
        self._agent = text.strip()
        if self._live_log:
            self._emit(_label("agent", self._agent))
            return
        self._redraw()

    def note_decision(self, outcome: str, score: float, chamber: str | None) -> None:
        self._decision = outcome.upper()
        self._score = score
        self._chamber = chamber or ""
        if outcome.lower() in {"hold", "no_action"}:
            return
        if self._live_log:
            self._show_hud()
            return
        self._redraw()

    async def show(self) -> None:
        self._show_hud()

    async def hide(self) -> None:
        if self._split:
            self._stream.write("\033[r\033[?25h\n")
            self._stream.flush()
            self._split = False
            return
        if self._tty:
            self._stream.write("\n")
            self._stream.flush()

    async def set_state(self, state: Any) -> None:
        name = getattr(state, "value", str(state))
        if name == "speaking":
            self._busy = False
        elif self._busy and name in {"idle", "chambered", "listening"}:
            self.states.append(name)
            return
        changed = name != self._state
        self._state = name
        self.states.append(name)
        if not changed:
            return
        if self._live_log:
            self._show_hud()
        elif not self._live_log:
            self._redraw()

    async def react(self, event: Any) -> None:  # noqa: ARG002
        return

    def stream_agent(self, delta: str) -> None:
        if not delta:
            return
        self._busy = False
        if self._live_log and not self._agent:
            self._stream.write(_label("agent", ""))
        self._agent += delta
        if self._live_log:
            self._stream.write(delta)
            self._stream.flush()
            return
        self._redraw()

    def note_level(self, rms: float, *, floor: float | None = None) -> None:
        """Push one mic frame into the traveling waveform (not a thinking spin)."""
        noise = 180.0 if floor is None else max(40.0, float(floor))
        span = max(1200.0, noise * 6.0)
        energy = min(1.0, max(0.0, float(rms) / span))
        self._rms = float(rms)
        self._energy = energy
        self._floor_energy = min(1.0, max(0.0, noise / span))
        self._levels.append(energy)
        self._spin += 0.08 + energy * 0.9
        if self._busy and self._busy_since and time.monotonic() - self._busy_since > 12:
            self.clear_busy()
        if energy > 0.08 and self._state == "idle":
            self._state = "listening"
            self._chamber = "listening"
        self._show_hud()

    def note_rt(self, detail: str) -> None:
        self._rt = (detail or "")[:72]
        if voice_debug_enabled():
            self._show_hud()

    def note_tool(self, detail: str) -> None:
        raw = (detail or "").strip()
        name = raw.split(None, 1)[0] if raw else ""
        extra = raw.split(None, 1)[1] if raw and " " in raw else ""
        if name.lower() == "tool" and extra:
            name = extra.split(None, 1)[0]
            extra = extra.split(None, 1)[1] if " " in extra else ""
        self._tool = tool_hint(name, extra)[:72]
        self._chamber = self._tool
        self._show_hud(force=True)

    def note_working(self, text: str) -> None:
        """Flip the HUD into a visible thinking state (spiral + hint)."""
        self._busy = True
        self._busy_since = time.monotonic()
        self._state = "thinking"
        self._decision = "THINK"
        self._chamber = text.strip() or "working it out"
        self._show_hud(force=True)

    def clear_busy(self) -> None:
        if not self._busy:
            return
        self._busy = False
        if self._state == "thinking":
            self._state = "idle"
            self._decision = "—"
            if self._live_log:
                self._show_hud()
            elif self._tty:
                self._redraw()

    def pulse(self) -> None:
        """Advance the thinking spiral. Cheap no-op unless the orb is thinking."""
        swirling = self._busy or self._state in {"thinking", "chambered", "confused"}
        if not swirling:
            return
        self._spin += 0.38 if (self._busy or self._state == "thinking") else 0.14
        self._show_hud()

    def _hud_lines(self) -> list[str]:
        try:
            from hosaka.tui.style import render_orb, render_orb_spiral, render_waveform, divider
        except Exception:  # noqa: BLE001
            render_orb = lambda _n: ""  # noqa: E731
            render_orb_spiral = lambda _p, **_k: ""  # noqa: E731
            render_waveform = lambda _lv, width=48, **_k: "  " + ("▁" * width)  # noqa: E731
            divider = lambda *_a, **_k: "  ─"  # noqa: E731
        swirling = self._busy or self._state in {"thinking", "chambered", "confused"}
        hint = (self._chamber or "listening").replace("\n", " ")[:42]
        debug = voice_debug_enabled()
        dot = {
            "listening": "●",
            "thinking": "◌",
            "speaking": "◉",
            "chambered": "○",
            "interrupted": "✕",
        }.get(self._state, "·")
        if debug:
            status = f"  {dot} {self._state:<11} rms {self._rms:5.0f}  {hint}"
        else:
            status = f"  {dot} {hint}"
        wave = render_waveform(
            list(self._levels), width=48, floor=self._floor_energy
        )
        rt = f"  rt       {(self._rt or '—')}"
        you = f"  you      {(self._user or '—')[:52]}"
        tool = f"  {(self._tool or '')[:52]}"
        if self._compact:
            lines = ["", wave, status, you]
            if self._tool:
                lines.append(tool)
            if debug:
                lines.append(rt)
            lines.append(divider(46))
            while len(lines) < self._hud_rows:
                lines.append("")
            return lines[: self._hud_rows]
        if swirling or self._energy > 0.12:
            orb = render_orb_spiral(self._spin, energy=self._energy).splitlines()
        else:
            intensity = _ORB_INTENSITY.get(self._state, 0)
            orb = render_orb(intensity).splitlines()
        lines = [""]
        lines.extend(orb)
        extra = ["", wave, status, you]
        if debug:
            extra.insert(3, rt)
        extra.append(divider(46))
        lines.extend(extra)
        while len(lines) < self._hud_rows:
            lines.append("")
        return lines[: self._hud_rows]

    def _enter_split(self) -> None:
        if self._split or not self._tty:
            return
        _cols, rows = _term_size()
        if rows >= HUD_ROWS + 6:
            self._hud_rows = HUD_ROWS
            self._compact = False
        elif rows >= HUD_ROWS_COMPACT + 4:
            self._hud_rows = HUD_ROWS_COMPACT
            self._compact = True
        else:
            return
        self._rows = rows
        self._split = True
        hud = "\n".join(line + "\033[K" for line in self._hud_lines())
        self._last_hud = hud
        self._stream.write(
            f"\033[?25l\033[2J\033[H{hud}\n"
            f"\033[{self._hud_rows + 1};{rows}r\033[{self._hud_rows + 1};1H"
        )
        self._stream.flush()

    def _paint_hud(self) -> None:
        if not self._split:
            self._enter_split()
            if not self._split:
                self._redraw()
                return
        hud = "\n".join(line + "\033[K" for line in self._hud_lines())
        if hud == self._last_hud:
            return
        self._last_hud = hud
        self._stream.write(f"\033[s\033[1;1H{hud}\033[u")
        self._stream.flush()

    def _block(self) -> str:
        try:
            from hosaka.tui.style import render_orb, render_orb_spiral
        except Exception:  # noqa: BLE001
            render_orb = lambda _n: ""  # noqa: E731
            render_orb_spiral = lambda _p: ""  # noqa: E731
        swirling = self._busy or self._state in {"thinking", "chambered", "confused"}
        art = render_orb_spiral(self._spin) if swirling else render_orb(
            _ORB_INTENSITY.get(self._state, 0)
        )
        status = render_social_status(
            self._state, self._decision, self._chamber, score=self._score
        )
        you = f"  [you]    {self._user}" if self._user else "  [you]"
        agent = f"  [hosaka] {self._agent}" if self._agent else "  [hosaka]"
        return "\n".join(
            ["", art, "", status, you, agent, ""]
        )

    def _redraw(self) -> None:
        block = self._block()
        if block == self._last_block:
            return
        self._last_block = block
        if not self._tty:
            log.info("social %s", render_social_status(
                self._state, self._decision, self._chamber, score=self._score
            ).strip())
            return
        if self._height:
            self._stream.write(f"\033[{self._height}A\033[J")
        self._stream.write(block)
        self._stream.flush()
        self._height = block.count("\n")

    def _emit(self, line: str) -> None:
        if self._live_log and self._tty:
            self._enter_split()
        self._stream.write(line.rstrip() + "\n")
        self._stream.flush()


class RealtimeTtsSink:
    """SpeechSink over the existing Realtime audio → Speaker path."""

    def __init__(self, session: Any, speaker: Any, *, hud: TuiOrbFace | None = None, claim: Any | None = None) -> None:
        self.session = session
        self.speaker = speaker
        self.hud = hud
        self.claim = claim
        self.requests: list[str] = []
        self.cancel_count = 0
        self._speaking = False

    async def speak(self, request: Any) -> None:
        if self.claim is not None and not self.claim():
            return
        text = str(getattr(request, "text", "") or "")
        self.requests.append(text)
        self._speaking = True
        if self.hud is not None:
            self.hud.note_agent(text)
        else:
            sys.stdout.write(f"\n[hosaka] {text}\n")
            sys.stdout.flush()
        speak = getattr(self.session, "speak_verbatim", None)
        if speak is not None:
            await speak(text)

    async def cancel(self) -> None:
        self.cancel_count += 1
        self._speaking = False
        cancel = getattr(self.session, "cancel_response", None)
        if cancel is not None:
            try:
                await cancel()
            except Exception:  # noqa: BLE001
                log.debug("realtime cancel failed", exc_info=True)
        abort = getattr(self.speaker, "abort", None)
        if abort is not None:
            await asyncio.to_thread(abort)

    def is_speaking(self) -> bool:
        return self._speaking

    def mark_completed(self) -> None:
        self._speaking = False


class HostLLMProvider:
    """Picoclaw-first, OpenAI-fallback structured provider. Host-side only."""

    provider_id = "hosaka_host"

    async def generate_text(
        self,
        messages: list[Any],
        *,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> str:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._chat, messages, timeout_seconds),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ""

    async def generate_structured(
        self,
        messages: list[Any],
        response_model: type[Any],
        *,
        temperature: float,
        timeout_seconds: float,
    ) -> Any:
        from hosaka_social.providers.base import StructuredOutputError

        schema = response_model.model_json_schema()
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Return ONLY JSON matching this schema. "
                    "No thought, no markdown. candidate_worth_generating "
                    "should usually be false unless Hosaka was addressed "
                    "or a short useful callback is clearly warranted.\n"
                    f"{json.dumps(schema)}"
                ),
            },
            *[
                {
                    "role": getattr(m, "role", "user"),
                    "content": getattr(m, "content", str(m)),
                }
                for m in messages
            ],
        ]
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._chat, prompt_messages, timeout_seconds),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise StructuredOutputError(
                f"reflection timed out after {timeout_seconds}s"
            ) from exc
        blob = _extract_json(raw)
        try:
            return response_model.model_validate_json(blob)
        except Exception as exc:
            raise StructuredOutputError(str(exc)) from exc

    async def health(self) -> Any:
        from hosaka_social.providers.base import ProviderHealth

        return ProviderHealth.HEALTHY

    def _chat(self, messages: list[Any], timeout: float = 120.0) -> str:
        from hosaka.llm import openai_adapter, picoclaw_adapter

        if isinstance(messages, str):
            text = messages
            msgs = [{"role": "user", "content": text}]
        else:
            msgs = messages
            text = "\n".join(str(m.get("content", "")) for m in msgs)
        if openai_adapter.is_available():
            try:
                return openai_adapter.chat_sync(msgs, timeout=timeout)
            except Exception:  # noqa: BLE001
                log.debug("openai reflection failed", exc_info=True)
        if picoclaw_adapter.is_available():
            try:
                return picoclaw_adapter.chat_sync(
                    text, session="hosaka:social", timeout=timeout
                )
            except Exception:  # noqa: BLE001
                log.debug("picoclaw reflection failed", exc_info=True)
        return ""


def _extract_json(raw: str) -> str:
    match = _JSON_RE.search(raw or "")
    return match.group(0) if match else (raw or "{}")


class VoiceSocialBridge:
    """Maps Realtime VAD/transcripts into SocialEngine for one voice turn."""

    def __init__(
        self,
        session: Any,
        speaker: Any,
        *,
        provider: Any | None = None,
        clock: Any | None = None,
        face: Any | None = None,
        face_stream: Any | None = None,
    ) -> None:
        from hosaka_social import SocialEngine, SystemClock
        from hosaka_social.social.governor import DecisionTrace

        self.face = face or TuiOrbFace(
            stream=face_stream if face_stream is not None else sys.__stdout__,
            live_log=True,
        )
        self.sink = RealtimeTtsSink(
            session, speaker, hud=self.face, claim=self._claim_response
        )
        self._session = session
        self._speaker = speaker
        self._tick_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._chatty = chatty_enabled()
        self._reflect_in_bg = provider is None and not self._chatty
        self._response_pending = False
        self._partial = ""

        def _on_decision(trace: DecisionTrace) -> None:
            chamber = self.engine.chamber.current
            self.face.note_decision(
                trace.outcome.value,
                trace.score,
                chamber.content if chamber else None,
            )

        self.engine = SocialEngine(
            clock=clock or SystemClock(),
            provider=provider or HostLLMProvider(),
            speech_sink=self.sink,
            face=self.face,
            auto_reflect=False,
            on_decision=_on_decision,
        )

    def _claim_response(self) -> bool:
        if self._response_pending:
            return False
        self._response_pending = True
        return True

    def _spawn(self, coro: Any) -> None:
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _ask(self) -> None:
        if self._chatty:
            return
        ask = getattr(self._session, "request_response", None)
        if ask is None or not self._claim_response():
            return
        self.face.note_working("working it out")
        await ask()

    async def _reflect_later(self) -> None:
        timeout = float(os.getenv("HOSAKA_SOCIAL_REFLECT_TIMEOUT", "6"))
        try:
            await self.engine.reflect_chambered(timeout_seconds=timeout)
        except Exception:  # noqa: BLE001
            log.debug("chambered reflection failed", exc_info=True)

    def attach(self) -> None:
        session = self._session
        speaker = self._speaker

        def _echoing() -> bool:
            return self.sink.is_speaking() or (
                callable(getattr(speaker, "recently_played", None))
                and speaker.recently_played()
            )

        async def _on_audio(pcm: bytes) -> None:
            self.sink._speaking = True
            speaker.play(pcm)

        async def _on_partial(delta: str) -> None:
            from hosaka_social.events import TranscriptPartial

            if _echoing() or not delta:
                return
            self._partial += delta
            shown = repair_transcript(self._partial)
            self.face.note_partial(shown)
            await self.engine.handle(
                TranscriptPartial(
                    speaker_id="operator",
                    text=shown,
                    stability=0.5 if len(shown.split()) < 3 else 0.9,
                )
            )
            if looks_directed(shown) and parse_play_command(shown) is None and parse_read_command(shown) is None:
                await self._ask()

        async def _on_user(text: str) -> None:
            from hosaka_social.events import TranscriptFinalized

            if _echoing():
                return
            repaired = repair_transcript(text)
            directed = looks_directed(repaired)
            shown = repaired if repaired.lower() != text.strip().lower() else text.strip()
            self._partial = ""
            self.face.note_user(shown)
            read = parse_read_command(repaired)
            game = None if read else parse_play_command(repaired)
            if directed and game is None and read is None:
                await self._ask()
            await self.engine.handle(
                TranscriptFinalized(
                    speaker_id="operator",
                    text=repaired,
                    addressed_agent_probability=1.0 if directed else 0.15,
                )
            )
            if game:
                from hosaka.voice.tools import dispatch

                self.face.note_working(f"launching {game}")
                result = await asyncio.to_thread(dispatch, "play_game", {"name": game})
                self.face.clear_busy()
                speak = getattr(session, "speak_verbatim", None)
                if speak is not None and self._claim_response():
                    await speak(result)
                return
            if read:
                from hosaka.voice.tools import dispatch

                name = (read.get("name") or "").strip()
                if read.get("action") == "list":
                    self.face.note_working("checking the shelf")
                    result = await asyncio.to_thread(dispatch, "list_books", {})
                else:
                    hint = f"opening {name}" if name else "opening the reader"
                    self.face.note_working(hint)
                    args = {"name": name} if name else {}
                    result = await asyncio.to_thread(dispatch, "open_reader", args)
                self.face.clear_busy()
                speak = getattr(session, "speak_verbatim", None)
                if speak is not None and self._claim_response():
                    await speak(result)
                return
            if self._reflect_in_bg:
                self._spawn(self._reflect_later())

        async def _on_assistant(delta: str) -> None:
            self.face.stream_agent(delta)

        async def _on_state(state: str) -> None:
            from hosaka_social.events import AudioActivityEnded, AudioActivityStarted

            if state == "listening":
                self.face.note_hearing()
                await self.engine.handle(
                    AudioActivityStarted(speaker_hint="operator", confidence=1.0)
                )
            elif state == "thinking":
                self.face.note_working("working it out")
                await self.engine.handle(AudioActivityEnded(duration_ms=0))
            elif state == "idle":
                await self.engine.handle(AudioActivityEnded(duration_ms=0))

        async def _on_done() -> None:
            self._response_pending = False
            self.face.clear_busy()
            self.sink.mark_completed()
            await self.engine.notify_speech_completed()

        session.on_audio = _on_audio
        session.on_user_partial = _on_partial
        session.on_user_transcript = _on_user
        session.on_assistant_transcript = _on_assistant
        session.on_state = _on_state
        session.on_response_done = _on_done

    async def run_ticks(self) -> None:
        try:
            while True:
                await self.engine.tick()
                self.face.pulse()
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise

    async def start_ticks(self) -> None:
        self._tick_task = asyncio.create_task(self.run_ticks())

    async def stop_ticks(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        task = self._tick_task
        self._tick_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.face.hide()
