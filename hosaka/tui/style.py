"""ANSI terminal styling utilities for the Hosaka console.

Provides color helpers, the orb mascot, gradient text, and box drawing.
All output uses ANSI escape sequences — no external dependencies.
"""

from __future__ import annotations

import math
import os
import random
import sys
import threading

# ── color toggle ─────────────────────────────────────────────────────────

def _color_enabled() -> bool:
    force = os.getenv("FORCE_COLOR", "").strip().lower()
    if force in {"1", "true", "yes", "on"}:
        return True
    if os.getenv("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "fileno"):
        return False
    try:
        return os.isatty(sys.stdout.fileno())
    except Exception:
        return True  # assume color OK if we can't tell


COLOR = _color_enabled()

# ── ANSI helpers ─────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"


def fg256(n: int) -> str:
    """Foreground color from the 256-color palette."""
    return f"\033[38;5;{n}m" if COLOR else ""


def bg256(n: int) -> str:
    """Background color from the 256-color palette."""
    return f"\033[48;5;{n}m" if COLOR else ""


def rgb(r: int, g: int, b: int) -> str:
    """24-bit true-color foreground."""
    return f"\033[38;2;{r};{g};{b}m" if COLOR else ""


def bg_rgb(r: int, g: int, b: int) -> str:
    """24-bit true-color background."""
    return f"\033[48;2;{r};{g};{b}m" if COLOR else ""


def _r() -> str:
    return RESET if COLOR else ""


# ── named palette ────────────────────────────────────────────────────────
# Cyberdeck-inspired: cyan, amber, violet, dim blue, soft green

CYAN = fg256(51)
CYAN_DIM = fg256(37)
AMBER = fg256(214)
AMBER_DIM = fg256(172)
VIOLET = fg256(135)
VIOLET_DIM = fg256(97)
GREEN = fg256(48)
GREEN_DIM = fg256(35)
BLUE = fg256(33)
BLUE_DIM = fg256(25)
WHITE = fg256(255)
GRAY = fg256(245)
DARK_GRAY = fg256(238)
RED = fg256(196)
PINK = fg256(213)

B = BOLD if COLOR else ""
D = DIM if COLOR else ""
R = RESET if COLOR else ""


# ── gradient text ────────────────────────────────────────────────────────

def gradient_text(text: str, colors: list[int] | None = None) -> str:
    """Apply a horizontal gradient across text using 256-color codes."""
    if not COLOR:
        return text
    if colors is None:
        # Cyan → Blue → Violet default gradient
        colors = [51, 45, 39, 33, 27, 63, 99, 135]
    result = []
    visible = 0
    for ch in text:
        if ch in (" ", "\n"):
            result.append(ch)
        else:
            idx = visible % len(colors)
            result.append(f"{fg256(colors[idx])}{ch}")
            visible += 1
    result.append(_r())
    return "".join(result)


def gradient_line(text: str, start_color: int, end_color: int) -> str:
    """Simple linear gradient between two 256-color values."""
    if not COLOR:
        return text
    length = max(1, len(text.replace(" ", "")))
    result = []
    visible = 0
    for ch in text:
        if ch == " ":
            result.append(ch)
        else:
            t = visible / max(1, length - 1)
            c = int(start_color + (end_color - start_color) * t)
            result.append(f"{fg256(c)}{ch}")
            visible += 1
    result.append(_r())
    return "".join(result)


# ── box drawing ──────────────────────────────────────────────────────────

def box(title: str, width: int = 39, color: str = "") -> list[str]:
    """Return a 3-line box with a centered title."""
    c = color if COLOR else ""
    r = _r()
    inner = width - 2
    padded = title.center(inner)
    return [
        f"  {c}┌{'─' * inner}┐{r}",
        f"  {c}│{r}{B}{padded}{R}{c}│{r}",
        f"  {c}└{'─' * inner}┘{r}",
    ]


def section_header(title: str, color: str = "") -> str:
    """Category header for command listings."""
    c = color if COLOR else ""
    r = _r()
    return f"\n  {c}── {title} ──{r}"


# ── the orb ──────────────────────────────────────────────────────────────
# An omniscient glowing orb that shifts hue and brightness.

# Orb states — each is a tuple of (art_lines, description)
# The orb uses unicode block/shade chars for glow effect.

_ORB_FRAMES = [
    # Dim / resting
    [
        "          ░░░░░          ",
        "       ░░░░░░░░░░░       ",
        "     ░░░░░▒▒▒▒▒░░░░░     ",
        "    ░░░░▒▒▒▒▒▒▒▒▒░░░░    ",
        "   ░░░░▒▒▒▒███▒▒▒▒░░░░   ",
        "   ░░░▒▒▒██████▒▒▒░░░░   ",
        "   ░░░░▒▒▒▒███▒▒▒▒░░░░   ",
        "    ░░░░▒▒▒▒▒▒▒▒▒░░░░    ",
        "     ░░░░░▒▒▒▒▒░░░░░     ",
        "       ░░░░░░░░░░░       ",
        "          ░░░░░          ",
    ],
    # Medium / attentive
    [
        "          ▒▒▒▒▒          ",
        "       ▒▒▒▒▒▒▒▒▒▒▒       ",
        "     ▒▒▒▒▒▓▓▓▓▓▒▒▒▒▒     ",
        "    ▒▒▒▒▓▓▓▓▓▓▓▓▓▒▒▒▒    ",
        "   ▒▒▒▒▓▓▓▓███▓▓▓▓▒▒▒▒   ",
        "   ▒▒▒▓▓▓████████▓▓▒▒▒   ",
        "   ▒▒▒▒▓▓▓▓███▓▓▓▓▒▒▒▒   ",
        "    ▒▒▒▒▓▓▓▓▓▓▓▓▓▒▒▒▒    ",
        "     ▒▒▒▒▒▓▓▓▓▓▒▒▒▒▒     ",
        "       ▒▒▒▒▒▒▒▒▒▒▒       ",
        "          ▒▒▒▒▒          ",
    ],
    # Bright / alert
    [
        "          ▓▓▓▓▓          ",
        "       ▓▓▓▓▓▓▓▓▓▓▓       ",
        "     ▓▓▓▓▓█████▓▓▓▓▓     ",
        "    ▓▓▓▓█████████▓▓▓▓    ",
        "   ▓▓▓▓████▀▀▀████▓▓▓▓   ",
        "   ▓▓▓████▀░░░▀████▓▓▓   ",
        "   ▓▓▓▓████▄▄▄████▓▓▓▓   ",
        "    ▓▓▓▓█████████▓▓▓▓    ",
        "     ▓▓▓▓▓█████▓▓▓▓▓     ",
        "       ▓▓▓▓▓▓▓▓▓▓▓       ",
        "          ▓▓▓▓▓          ",
    ],
    # Blazing / activated
    [
        "     ·    █████    ·     ",
        "   ·   ███████████   ·   ",
        "     █████████████████     ",
        "    ███████████████████    ",
        "   ████████▀▀▀████████   ",
        "   ███████▀ ◉ ▀███████   ",
        "   ████████▄▄▄████████   ",
        "    ███████████████████    ",
        "     █████████████████     ",
        "   ·   ███████████   ·   ",
        "     ·    █████    ·     ",
    ],
]

# Color palettes for each orb state
_ORB_PALETTES = [
    # Dim: deep blue
    (23, 25, 27),
    # Medium: cyan
    (30, 37, 44),
    # Bright: bright cyan
    (39, 45, 51),
    # Blazing: white-cyan with glow
    (51, 195, 231),
]


def render_orb(state: int = 0) -> str:
    """Render the orb at a given intensity state (0=dim, 3=blazing).

    Returns a complete multi-line string ready to print.
    """
    state = max(0, min(3, state))
    frame = _ORB_FRAMES[state]
    c1, c2, c3 = _ORB_PALETTES[state]

    lines = []
    for row in frame:
        colored = []
        for ch in row:
            if ch == "█":
                colored.append(f"{fg256(c3)}{ch}")
            elif ch == "▓":
                colored.append(f"{fg256(c2)}{ch}")
            elif ch in ("▒", "▀", "▄"):
                colored.append(f"{fg256(c2)}{ch}")
            elif ch == "░":
                colored.append(f"{fg256(c1)}{ch}")
            elif ch == "◉":
                colored.append(f"{fg256(231)}{B}{ch}{R}")
            elif ch == "·":
                colored.append(f"{fg256(c1)}{ch}")
            else:
                colored.append(ch)
        colored.append(_r())
        lines.append("  " + "".join(colored))
    return "\n".join(lines)


def random_orb() -> str:
    """Render the orb at a random intensity."""
    weights = [40, 35, 20, 5]  # mostly dim, rarely blazing
    state = random.choices(range(4), weights=weights, k=1)[0]  # noqa: S311
    return render_orb(state)


_SPIRAL_CHARS = " ·░▒▓█"
_SPIRAL_PALETTE = (23, 25, 30, 37, 45, 51, 87)


def render_orb_spiral(phase: float, energy: float = 0.0) -> str:
    """Two-arm galaxy swirl. ``energy`` 0–1 punches the arms from mic RMS."""
    width, height = 25, 11
    cx, cy = 12.0, 5.0
    punch = 0.55 + 0.9 * max(0.0, min(1.0, energy))
    lines: list[str] = []
    for row in range(height):
        cells: list[str] = []
        for col in range(width):
            dx = (col - cx) * 0.42
            dy = row - cy
            radius = math.hypot(dx, dy)
            if radius > 6.35:
                cells.append(" ")
                continue
            if radius < 0.85:
                cells.append(f"{fg256(231)}{B}◉{R}")
                continue
            theta = math.atan2(dy, dx)
            swirl = theta * 2.0 - radius * 1.15 + phase
            arm = 0.5 + 0.5 * math.cos(swirl)
            arm2 = 0.5 + 0.5 * math.cos(swirl * 0.5 + 1.2)
            core = max(0.0, 1.0 - (radius / 6.35) ** 1.6)
            value = max(arm, arm2 * 0.55) * core * punch
            idx = min(5, int(value * 6.2))
            ch = _SPIRAL_CHARS[idx]
            if ch == " ":
                cells.append(" ")
                continue
            pal = _SPIRAL_PALETTE[min(len(_SPIRAL_PALETTE) - 1, idx)]
            cells.append(f"{fg256(pal)}{ch}")
        cells.append(_r())
        lines.append("  " + "".join(cells))
    return "\n".join(lines)


_WAVE_BARS = " ▁▂▃▄▅▆▇█"


def render_waveform(levels: list[float], width: int = 48, *, floor: float = 0.0) -> str:
    """Traveling RMS meter. Newest sample is on the right.

    Samples at or below ``floor`` render dim so the noise floor is visible.
    """
    if width < 8:
        width = 8
    data = list(levels)[-width:]
    if len(data) < width:
        data = [0.0] * (width - len(data)) + data
    dim_cut = max(0.0, float(floor)) + 0.02
    cells: list[str] = []
    for v in data:
        idx = min(8, max(0, int(v * 9)))
        ch = _WAVE_BARS[idx]
        color = DARK_GRAY if v <= dim_cut else CYAN
        cells.append(f"{color}{ch}" if COLOR else ch)
    return f"  {''.join(cells)}{_r()}"


# ── decorative elements ──────────────────────────────────────────────────

def divider(width: int = 50, color: str = "") -> str:
    c = color or DARK_GRAY
    return f"  {c}{'─' * width}{_r()}" if COLOR else f"  {'─' * width}"


def sparkle_line(width: int = 50) -> str:
    """A line of random subtle sparkle chars."""
    if not COLOR:
        return ""
    chars = "·.·:·.·.·:··.·.·:·.·.·:··.·.·:·.·.·:··.·.·:·.·"
    line = chars[:width]
    return f"  {DARK_GRAY}{line}{_r()}"


class thinking_sparkles:
    """A comet of sparkles that flies while the model is thinking."""

    def __init__(self, width: int = 42) -> None:
        self.width = max(16, width)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> thinking_sparkles:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.4)
        self._clear()

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def _clear(self) -> None:
        try:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass

    def _run(self) -> None:
        trail = "·✦✧✦·"
        colors = [51, 45, 135, 213, 214]
        i = 0
        while not self._stop.wait(0.07):
            pos = (i % (self.width + len(trail) + 4)) - len(trail)
            cells: list[str] = []
            for col in range(self.width):
                k = col - pos
                if 0 <= k < len(trail):
                    cells.append(f"{fg256(colors[k % len(colors)])}{trail[k]}")
                else:
                    cells.append(" ")
            try:
                sys.stdout.write("\r  " + "".join(cells) + _r())
                sys.stdout.flush()
            except Exception:  # noqa: BLE001
                break
            i += 1


# ── colorize helpers for the console ─────────────────────────────────────

def cmd_style(text: str) -> str:
    """Style a command name."""
    return f"{CYAN}{text}{_r()}" if COLOR else text


def desc_style(text: str) -> str:
    """Style a description."""
    return f"{GRAY}{text}{_r()}" if COLOR else text


def label_style(text: str) -> str:
    """Style a label (e.g. 'Host:', 'Model:')."""
    return f"{CYAN_DIM}{text}{_r()}" if COLOR else text


def value_style(text: str) -> str:
    """Style a value."""
    return f"{WHITE}{text}{_r()}" if COLOR else text


def ok_style(text: str) -> str:
    return f"{GREEN}{text}{_r()}" if COLOR else text


def warn_style(text: str) -> str:
    return f"{AMBER}{text}{_r()}" if COLOR else text


def err_style(text: str) -> str:
    return f"{RED}{text}{_r()}" if COLOR else text


def lore_style(text: str) -> str:
    """Style for lore fragments — eerie violet."""
    return f"{VIOLET_DIM}{text}{_r()}" if COLOR else text


_TERM_RESET = "\033[r\033[?25h"
_GUARD_INSTALLED = False


def restore_terminal() -> None:
    """Undo DECSTBM split-pane + hidden cursor if voice HUD died mid-draw."""
    for stream in (getattr(sys, "__stdout__", None), getattr(sys, "stdout", None)):
        if stream is None:
            continue
        try:
            stream.write(_TERM_RESET)
            stream.flush()
            break
        except Exception:  # noqa: BLE001
            continue


def install_terminal_guard() -> None:
    """atexit + excepthook so a crash doesn't leave the TTY broken."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    _GUARD_INSTALLED = True
    import atexit

    atexit.register(restore_terminal)
    previous = sys.excepthook

    def _hook(exc_type, exc, tb) -> None:  # noqa: ANN001
        restore_terminal()
        previous(exc_type, exc, tb)

    sys.excepthook = _hook
    pin_to_tui()


def tui_escape_allowed() -> bool:
    default = "1" if sys.platform == "darwin" else "0"
    raw = os.getenv("HOSAKA_ALLOW_SHELL", default).strip().lower()
    return raw not in {"0", "false", "no", "off", ""}


def pin_to_tui() -> None:
    """Disable job-control so Ctrl-Z cannot drop the operator into bash."""
    if tui_escape_allowed():
        return
    import signal

    for sig in (signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU, signal.SIGQUIT):
        try:
            signal.signal(sig, signal.SIG_IGN)
        except (OSError, ValueError):
            pass
