# Jetson Offline Inference: HTTP WAV Milestone

This repository is canonical for both machines. The Raspberry Pi runs the
`main` role and owns microphone, speaker, display, controls, VAD, barge-in, and
the HTTP client. The Jetson runs the `server` role and never opens local audio
hardware.

## Pi setup

Install the existing core and Pi audio dependencies:

```bash
cd ~/Hosaka
sudo apt-get install -y python3-venv alsa-utils avahi-daemon libnss-mdns
python -m venv .venv
.venv/bin/python -m pip install -r requirements-hosaka.txt
```

Prefer Jetson mDNS and optionally set a router-assigned IP fallback:

```bash
export HOSAKA_JETSON_URL=http://hosaka-jetson.local:8421
export HOSAKA_JETSON_FALLBACK_URL=http://JETSON_LAN_IP:8421
export HOSAKA_INFERENCE_TOKEN=YOUR_SHARED_TOKEN
```

Send an existing 16 kHz mono PCM16 WAV and play the returned WAV:

```bash
hosaka inference speech-16k-mono.wav
```

Or record five seconds on the Pi, submit it, and play the response:

```bash
hosaka inference --record 5
```

Press `Ctrl+C` to cancel the request or local `aplay` process immediately.
Convert another recording when needed:

```bash
ffmpeg -i source.wav -ar 16000 -ac 1 -c:a pcm_s16le speech-16k-mono.wav
```

## Jetson launch boundary

After the Jetson implementation supplies the bytes-only inference responder:

```bash
cd ~/Hosaka
python -m venv .venv
.venv/bin/python -m pip install -r requirements-hosaka.txt
export HOSAKA_INFERENCE_TOKEN=YOUR_SHARED_TOKEN
.venv/bin/python -m hosaka.server_role
```

The current unprovisioned server intentionally returns `503` from `/respond`.
It does not import audio hardware packages, download models, contact cloud
providers, or silently fall back to OpenAI. Jetson provider installation and
hardware validation are deferred to the Jetson role owner.