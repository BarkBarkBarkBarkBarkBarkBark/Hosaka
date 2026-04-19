#!/usr/bin/env python3
"""Dump the live FastAPI OpenAPI schema to a file.

Used by the docs CI workflow so the published API reference always matches
the code in this commit. Run locally with:

    python scripts/dump_openapi.py docs/openapi.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Avoid loading state on disk when we just want the schema.
os.environ.setdefault("HOSAKA_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hosaka.web.server import app  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/openapi.json")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
