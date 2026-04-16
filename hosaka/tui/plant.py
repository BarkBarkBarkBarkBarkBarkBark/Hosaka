"""The Hosaka plant — an alien organism that grows with use and wilts with neglect.

States (0-6):
  0 = dead    — a withered stalk, no color
  1 = wilted  — drooping, faded
  2 = dry     — alive but struggling
  3 = stable  — modest healthy plant
  4 = growing — lush, small buds
  5 = bloom   — flowering, vibrant
  6 = colony  — has reproduced, multiple growths

Mechanics:
  - Each console command interaction adds vitality points
  - Time without interaction drains vitality
  - Vitality maps to a plant state
  - State persists to ~/.hosaka/plant.json
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hosaka.tui.style import (
    AMBER, CYAN, DARK_GRAY, DIM, GREEN, GREEN_DIM, GRAY, PINK, R, RED,
    VIOLET, VIOLET_DIM, WHITE, fg256,
)

_PLANT_PATH = Path.home() / ".hosaka" / "plant.json"

# ── vitality constants ───────────────────────────────────────────────────

VITALITY_PER_COMMAND = 3        # points gained per console interaction
VITALITY_DRAIN_PER_HOUR = 5     # points lost per hour of inactivity
VITALITY_MAX = 200              # ceiling
VITALITY_THRESHOLDS = [         # (min_vitality, state_index)
    (0,   0),   # dead
    (1,   1),   # wilted
    (15,  2),   # dry
    (40,  3),   # stable
    (80,  4),   # growing
    (130, 5),   # bloom
    (170, 6),   # colony
]
STATE_NAMES = ["dead", "wilted", "dry", "stable", "growing", "bloom", "colony"]


@dataclass
class PlantState:
    vitality: float = 30.0          # start at "stable-ish"
    last_interaction: float = 0.0   # unix timestamp
    total_commands: int = 0
    births: int = 0                 # times it reached colony state
    name: str = ""                  # player can name it eventually

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> PlantState:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _load() -> PlantState:
    if _PLANT_PATH.exists():
        try:
            return PlantState.from_dict(json.loads(_PLANT_PATH.read_text()))
        except Exception:
            pass
    return PlantState(last_interaction=time.time())


def _save(ps: PlantState) -> None:
    _PLANT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLANT_PATH.write_text(json.dumps(ps.to_dict(), indent=2))


def _apply_decay(ps: PlantState) -> None:
    """Drain vitality based on elapsed time since last interaction."""
    now = time.time()
    if ps.last_interaction <= 0:
        ps.last_interaction = now
        return
    elapsed_hours = (now - ps.last_interaction) / 3600.0
    if elapsed_hours > 0:
        drain = elapsed_hours * VITALITY_DRAIN_PER_HOUR
        ps.vitality = max(0, ps.vitality - drain)


def _state_index(vitality: float) -> int:
    idx = 0
    for threshold, state in VITALITY_THRESHOLDS:
        if vitality >= threshold:
            idx = state
    return idx


# ── public API ───────────────────────────────────────────────────────────

def record_interaction() -> None:
    """Call this on every console command to feed the plant."""
    ps = _load()
    _apply_decay(ps)
    ps.vitality = min(VITALITY_MAX, ps.vitality + VITALITY_PER_COMMAND)
    ps.last_interaction = time.time()
    ps.total_commands += 1
    old_state = _state_index(ps.vitality - VITALITY_PER_COMMAND)
    new_state = _state_index(ps.vitality)
    if new_state == 6 and old_state < 6:
        ps.births += 1
    _save(ps)


def get_plant_status() -> tuple[int, PlantState]:
    """Return (state_index, plant_state) after applying decay."""
    ps = _load()
    _apply_decay(ps)
    _save(ps)
    return _state_index(ps.vitality), ps


# ── ASCII art ────────────────────────────────────────────────────────────
# Each state is a list of strings.  Colors applied at render time.

_PLANT_ART: list[list[str]] = [
    # 0: dead
    [
        "          ",
        "     .    ",
        "     |    ",
        "     |    ",
        "    .|.   ",
        "   _|||_  ",
        "  [_____] ",
    ],
    # 1: wilted
    [
        "          ",
        "    ,     ",
        "    |\\    ",
        "    | )   ",
        "    |/    ",
        "   _|_    ",
        "  [_____] ",
    ],
    # 2: dry
    [
        "          ",
        "    \\ |   ",
        "     \\|   ",
        "     |    ",
        "     |    ",
        "   __|__  ",
        "  [_____] ",
    ],
    # 3: stable
    [
        "     _    ",
        "    ( )   ",
        "    \\|/   ",
        "     |    ",
        "     |    ",
        "   __|__  ",
        "  [_____] ",
    ],
    # 4: growing
    [
        "   \\ _ /  ",
        "   -( )-  ",
        "  / \\|    ",
        " (_) |/\\  ",
        "     |/   ",
        "   __|__  ",
        "  [_____] ",
    ],
    # 5: bloom
    [
        "  * \\ _ / ",
        "   @( )@  ",
        "  */\\|/\\* ",
        " (@)|  /\\ ",
        "  \\ | /(_)",
        "   _|_/_  ",
        "  [_____] ",
    ],
    # 6: colony
    [
        " *@* _ *@*",
        " \\@(*)@/ *",
        "*/\\\\|//\\@*",
        "(@)|  /\\(@",
        " *\\|*/(_)*",
        " __|_/__|_",
        " [___][__]",
    ],
]

# Color palettes per state: (stalk, leaf, flower, pot)
_PLANT_COLORS: list[tuple[str, str, str, str]] = [
    (DARK_GRAY, DARK_GRAY, DARK_GRAY, GRAY),       # dead
    (fg256(94),  fg256(58),  fg256(58),  GRAY),     # wilted — brown/olive
    (fg256(100), fg256(64),  fg256(64),  GRAY),     # dry — dull green
    (fg256(34),  GREEN_DIM,  GREEN_DIM,  GRAY),     # stable — green
    (fg256(34),  GREEN,      fg256(228), GRAY),     # growing — bright green, yellow buds
    (fg256(34),  GREEN,      PINK,       GRAY),     # bloom — pink flowers
    (fg256(34),  GREEN,      VIOLET,     CYAN),     # colony — violet blooms, cyan pot
]

_CHAR_ROLES = {
    "|": "stalk", "/": "stalk", "\\": "stalk",
    "(": "leaf", ")": "leaf", "_": "stalk",
    "@": "flower", "*": "flower",
    "[": "pot", "]": "pot",
    "-": "leaf",
}


def render_plant(state: int = 3) -> str:
    """Render the plant at a given state. Returns a multi-line string."""
    state = max(0, min(6, state))
    art = _PLANT_ART[state]
    stalk_c, leaf_c, flower_c, pot_c = _PLANT_COLORS[state]

    lines = []
    for row in art:
        colored = []
        for ch in row:
            if ch == " ":
                colored.append(ch)
            elif ch in ("@", "*"):
                colored.append(f"{flower_c}{ch}")
            elif ch in ("[", "]"):
                colored.append(f"{pot_c}{ch}")
            elif ch in ("(", ")", "-"):
                colored.append(f"{leaf_c}{ch}")
            elif ch == ".":
                colored.append(f"{DARK_GRAY}{ch}")
            else:
                colored.append(f"{stalk_c}{ch}")
        colored.append(R)
        lines.append("    " + "".join(colored))
    return "\n".join(lines)


def render_plant_status() -> str:
    """Full plant display with status info."""
    idx, ps = get_plant_status()
    name = STATE_NAMES[idx]

    art = render_plant(idx)

    # Status bar
    bar_len = 20
    filled = int((ps.vitality / VITALITY_MAX) * bar_len)
    bar_color = [RED, RED, fg256(208), fg256(214), GREEN_DIM, GREEN, GREEN][idx]
    bar = f"{bar_color}{'█' * filled}{DARK_GRAY}{'░' * (bar_len - filled)}{R}"

    lines = [
        "",
        art,
        "",
        f"    {GRAY}State:{R}    {_state_label(idx)}",
        f"    {GRAY}Vitality:{R} [{bar}] {GRAY}{ps.vitality:.0f}/{VITALITY_MAX}{R}",
        f"    {GRAY}Commands:{R} {WHITE}{ps.total_commands}{R}",
    ]
    if ps.births > 0:
        lines.append(f"    {GRAY}Colonies:{R} {VIOLET}{ps.births}{R}")

    # Flavor text
    flavor = _flavor_text(idx)
    lines.append(f"\n    {DARK_GRAY}{flavor}{R}")
    lines.append("")
    return "\n".join(lines)


def _state_label(idx: int) -> str:
    labels = [
        f"{DARK_GRAY}dead{R}",
        f"{RED}wilted{R}",
        f"{fg256(208)}dry{R}",
        f"{fg256(214)}stable{R}",
        f"{GREEN_DIM}growing{R}",
        f"{GREEN}blooming{R}",
        f"{VIOLET}colony{R}",
    ]
    return labels[idx]


def _flavor_text(idx: int) -> str:
    import random
    texts = [
        # dead
        [
            "A dry stalk. Whatever was here is gone.",
            "Nothing grows in silence forever.",
            "Perhaps it will return. Perhaps not.",
        ],
        # wilted
        [
            "It droops. It remembers better days.",
            "Still alive — barely. It could use attention.",
            "The roots hold, but the leaves have given up.",
        ],
        # dry
        [
            "Alive, but thirsty. Each command is water.",
            "It leans toward the cursor, hoping.",
            "Not thriving, but not surrendering either.",
        ],
        # stable
        [
            "A modest, healthy specimen.",
            "It seems content. For now.",
            "Growing at its own ancient pace.",
        ],
        # growing
        [
            "Buds forming. Something is about to happen.",
            "It responds to your presence. Curious thing.",
            "The leaves track your keystrokes.",
        ],
        # bloom
        [
            "In full flower. Alien petals catch no sunlight here.",
            "It blooms in radio waves and terminal glow.",
            "Beautiful, in a way that shouldn't exist.",
        ],
        # colony
        [
            "It has reproduced. A second growth emerges from the pot.",
            "Life finds a way, even in a terminal.",
            "The colony spreads. The signal is strong here.",
        ],
    ]
    return random.choice(texts[idx])  # noqa: S311


def banner_plant_hint(state: int) -> str:
    """A tiny one-line hint for the banner, showing plant health."""
    if state <= 0:
        return f"{DARK_GRAY}[plant: dead]{R}"
    if state <= 2:
        return f"{fg256(208)}[plant: needs attention]{R}"
    if state <= 4:
        return f"{GREEN_DIM}[plant: healthy]{R}"
    if state == 5:
        return f"{GREEN}[plant: blooming]{R}"
    return f"{VIOLET}[plant: colony]{R}"
