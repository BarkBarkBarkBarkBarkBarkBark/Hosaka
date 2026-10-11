from __future__ import annotations

import subprocess
import logging
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SCRIPT = APP_ROOT / "scripts" / "update_hosaka.sh"
log = logging.getLogger("hosaka.update")


def run_update() -> tuple[bool, str]:
    if not UPDATE_SCRIPT.exists():
        log.error("Update script not found: %s", UPDATE_SCRIPT)
        return False, f"Update script not found: {UPDATE_SCRIPT}"

    try:
        result = subprocess.run(["bash", str(UPDATE_SCRIPT)], capture_output=True, text=True, cwd=str(APP_ROOT))
    except OSError as exc:
        log.exception("Update failed to launch")
        return False, f"Update failed to launch: {exc}"

    output = "\n".join(chunk for chunk in [result.stdout.strip(), result.stderr.strip()] if chunk)
    if result.returncode != 0:
        log.error("Update failed: %s", output)
    return result.returncode == 0, output or f"Updater exited with status {result.returncode}."
