"""ANSI terminal styling utilities for the Hosaka console.

Provides color helpers, the orb mascot, gradient text, and box drawing.
All output uses ANSI escape sequences — no external dependencies.
"""

from __future__ import annotations

import os
import random
import sys

# ── color toggle ─────────────────────────────────────────────────────────

def _color_enabled() -> bool:
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
