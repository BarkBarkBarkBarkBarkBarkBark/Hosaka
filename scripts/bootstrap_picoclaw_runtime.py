#!/usr/bin/env python
"""Generate PicoClaw runtime files from Hosaka repo-owned sources."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from hosaka.picoclaw_runtime import main


if __name__ == "__main__":
    main()
