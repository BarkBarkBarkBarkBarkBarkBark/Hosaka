from __future__ import annotations

from pathlib import Path

# Load .env (repo root or cwd) before anything reads os.environ.
# This is a no-op when the file doesn't exist or vars are already set.
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(_env_file, override=False)
except ImportError:
    pass

from hosaka.boot.launcher import launch


if __name__ == "__main__":
    launch()
