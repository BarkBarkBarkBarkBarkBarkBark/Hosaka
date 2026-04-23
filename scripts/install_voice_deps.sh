#!/usr/bin/env bash
# install_voice_deps.sh — one-shot installer for Hosaka voice mode.
#
# Pulls the system libraries that the Python voice deps (sounddevice, opencv,
# openwakeword) need, then pip-installs from requirements-voice.txt.
#
# Safe to re-run. Designed for Raspberry Pi OS / Debian / Ubuntu.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

echo "[voice-deps] apt packages (portaudio, alsa, v4l)..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  portaudio19-dev \
  libasound2-dev \
  libsndfile1 \
  v4l-utils \
  ffmpeg

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  PIP=(pip install)
else
  PIP=(pip install --user)
fi

echo "[voice-deps] pip install -r requirements-voice.txt"
"${PIP[@]}" -r "$ROOT/requirements-voice.txt"

echo "[voice-deps] pre-downloading openwakeword models..."
python - <<'PY'
try:
    import openwakeword.utils as u
    u.download_models()
    print("  ok — openwakeword models cached in ~/.cache/openwakeword")
except Exception as exc:
    print(f"  skipped ({exc}) — will auto-download on first use")
PY

cat <<'NOTE'

[voice-deps] done.

Sanity checks you probably want to run:

  # list audio devices (note the USB mic / card number)
  python -c "import sounddevice as sd; print(sd.query_devices())"

  # list video devices
  v4l2-ctl --list-devices

  # set input / output if the defaults are wrong
  export HOSAKA_VOICE_INPUT_DEVICE=1
  export HOSAKA_VOICE_OUTPUT_DEVICE=1
  export HOSAKA_VOICE_CAMERA=/dev/video0

Set OPENAI_API_KEY in /etc/hosaka/env or ~/.picoclaw/config.json and then:

  hosaka voice         # headless daemon (wake-word + Realtime)

NOTE
