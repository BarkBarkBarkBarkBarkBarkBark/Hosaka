from __future__ import annotations

import subprocess
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SCRIPT = APP_ROOT / "scripts" / "update_hosaka.sh"


def run_update() -> tuple[bool, str]:
    if not UPDATE_SCRIPT.exists():
        return False, f"Update script not found: {UPDATE_SCRIPT}"

    try:
        result = subprocess.run([str(UPDATE_SCRIPT)], capture_output=True, text=True, cwd=str(APP_ROOT))
    except Exception as exc:  # noqa: BLE001
        return False, f"Update failed to launch: {exc}"

    output = "\n".join(chunk for chunk in [result.stdout.strip(), result.stderr.strip()] if chunk)
    return result.returncode == 0, output or "Updater ran with no output."
