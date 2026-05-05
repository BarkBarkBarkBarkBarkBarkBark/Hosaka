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
#
# Tuned so casual use keeps the bonsai alive:
#
#   1 visit/day  →  +20 - 12 = +8 vitality/day  →  reaches "growing"
#   2 visits/day →  +28/day                       →  blooms in a week
#   0 visits/wk  →  -84/wk → still bloom from full
#   0 visits/2wk →  -168/2wk → dry but alive
#
# Pre-rewrite was 5 pts/hour drain (= 120/day) with +3/visit. Even daily
# use bottomed out instantly. The bonsai is meant to be a companion, not a
# performance evaluation.

VITALITY_PER_COMMAND = 20       # points gained per console interaction
VITALITY_DRAIN_PER_HOUR = 0.5   # points lost per hour of inactivity (~12/day)
VITALITY_MAX = 200              # ceiling
VITALITY_THRESHOLDS = [         # (min_vitality, state_index)
    (0,   0),   # dead
    (1,   1),   # wilted (any pulse keeps it alive)
    (10,  2),   # dry
    (30,  3),   # stable  — starting state
    (60,  4),   # growing — reachable from a single visit/day
    (110, 5),   # bloom
    (160, 6),   # colony
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
    # Each frame is exactly 7 rows. Char roles in render():
    #   ()-   leaf      @ *   flower      [ ]   pot
    #   |/\   stalk     .     dim ground  _     stalk (or pot rim)
    # 0: dead — bare leaning trunk
    [
        "          ",
        "          ",
        "     \\_   ",
        "      \\   ",
        "      /   ",
        "     /    ",
        "   [___]  ",
    ],
    # 1: wilted — one stubborn drooping leaf
    [
        "          ",
        "     _    ",
        "    ( )   ",
        "     \\    ",
        "     /    ",
        "     |    ",
        "   [___]  ",
    ],
    # 2: dry — sparse twigs, no leaves yet
    [
        "    \\ /   ",
        "     V    ",
        "     |    ",
        "     /    ",
        "    /     ",
        "    |     ",
        "   [___]  ",
    ],
    # 3: stable — small bonsai canopy
    [
        "    ___   ",
        "   ( . )  ",
        "    \\|/   ",
        "     /    ",
        "    /     ",
        "    |     ",
        "   [___]  ",
    ],
    # 4: growing — fuller cloud canopy
    [
        "   _ _ _  ",
        "  ( . . ) ",
        "   \\\\|//  ",
        "    \\|    ",
        "    /     ",
        "    |     ",
        "   [___]  ",
    ],
    # 5: bloom — flowers in the canopy
    [
        "  *_ _ _* ",
        " (@ . . @)",
        "  \\\\@|//  ",
        "    *|*   ",
        "     |    ",
        "     |    ",
        "   [___]  ",
    ],
    # 6: colony — twin trunks, moss along the rim
    [
        " *_ _* _ *",
        "(@ . )( @)",
        " \\\\|//\\|/",
        "   *|  /  ",
        "    | /   ",
        "    \\/    ",
        "  [.___.] ",
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
            "the bonsai has gone to ash. start a new one with /plant reset.",
            "silence in the pot. nothing answers the cursor.",
            "a dry stick. memory of leaves.",
        ],
        # wilted
        [
            "one stubborn leaf. it remembers you.",
            "a pulse, barely. a visit a day will bring it back.",
            "the roots hold. the canopy waits.",
        ],
        # dry
        [
            "twigs. dry but ready — each command is rain.",
            "the trunk leans toward the prompt.",
            "not thriving, not surrendering. patient.",
        ],
        # stable
        [
            "a small canopy. a steady companion.",
            "trimmed by use, balanced by neglect.",
            "the bonsai listens to your typing.",
        ],
        # growing
        [
            "two cloud-leaves form. shape begins.",
            "the canopy thickens with attention.",
            "good rhythm. it grows when you grow.",
        ],
        # bloom
        [
            "in flower. small alien petals on a small ancient tree.",
            "the pot hums faintly. blossoms catch the terminal glow.",
            "steady tending, full bloom.",
        ],
        # colony
        [
            "twin trunks. moss along the rim.",
            "life finds a way, even in a terminal pot.",
            "the colony holds. signal steady.",
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
