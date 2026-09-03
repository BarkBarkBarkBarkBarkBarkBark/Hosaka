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

## Jetson provider implementation

The server role now runs a bytes-only sequential provider pipeline:

1. whisper.cpp native Silero VAD and transcription on CPU
2. deterministic directed-speech participation gate
3. local Ollama `qwen3:4b` generation
4. Piper `en_US-lessac-medium` synthesis on CPU
5. conversion of Piper's native 22.05 kHz WAV to the shared 16 kHz WAV contract

It never imports microphone or speaker packages. CUDA Whisper is opt-in with
`HOSAKA_WHISPER_GPU=1`; CPU is the reliable default because Jetson unified-memory
fragmentation prevented a 140.5 MiB CUDA allocation during validation. Keep
Ollama loaded on the GPU and use CPU Whisper/Piper.

Installed artifacts on the validated Jetson:

| Artifact | Version/model |
|---|---|
| whisper.cpp | release `b4938` checkout (`whisper.cpp 1.9.3-dev`) |
| Default STT | `ggml-tiny.en.bin` with Hosaka vocabulary prompt |
| Accuracy fallback | `ggml-base.en.bin` |
| VAD | `ggml-silero-v6.2.0.bin` through whisper.cpp |
| Piper | `piper-tts 1.7.0`, GPL-3.0-or-later |
| Piper voice | `en_US-lessac-medium`, model card stored beside model |
| LLM | Ollama `qwen3:4b` |

Production startup runs `scripts/check-jetson-inference`, which verifies local
files and `/opt/hosaka/artifacts.sha256`. It performs no downloads.

Required `/etc/hosaka/inference.env` values:

```dotenv
HOSAKA_INFERENCE_HOST=0.0.0.0
HOSAKA_INFERENCE_PORT=8421
HOSAKA_INFERENCE_TOKEN=REPLACE_WITH_A_RANDOM_SHARED_TOKEN
HOSAKA_WHISPER_BIN=/opt/hosaka/bin/whisper-cli
HOSAKA_WHISPER_MODEL=/opt/hosaka/models/whisper/ggml-tiny.en.bin
HOSAKA_WHISPER_VAD_MODEL=/opt/hosaka/models/whisper/ggml-silero-v6.2.0.bin
HOSAKA_WHISPER_GPU=0
HOSAKA_OLLAMA_BASE_URL=http://127.0.0.1:11434
HOSAKA_OLLAMA_MODEL=qwen3:4b
HOSAKA_PIPER_BIN=/opt/hosaka/bin/piper
HOSAKA_PIPER_MODEL=/opt/hosaka/models/piper/en_US-lessac-medium.onnx
HOSAKA_PIPER_CONFIG=/opt/hosaka/models/piper/en_US-lessac-medium.onnx.json
```

Install the unit only on the Jetson:

```bash
sudo install -m 0755 scripts/check-jetson-inference /usr/local/bin/check-jetson-inference
sudo install -m 0644 systemd/hosaka-inference.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hosaka-inference.service
```

Health checks:

```bash
curl --fail http://127.0.0.1:8421/health
curl --fail http://127.0.0.1:8421/status
```

### Measured baseline

Measurements were captured on the Orin Nano with L4T R36.4.7, CUDA 12.6,
MAXN_SUPER, and an active desktop development session. Raw logs were stored in
`/tmp/hosaka-*.log` during validation.

| Test | Result |
|---|---|
| 11 s JFK, base.en CPU + VAD | 3.16 s wall; 68.5 ms VAD; correct transcript |
| 2.4 s addressed fixture, tiny.en CPU + VAD | 1.33 s wall; preserved `Hosaka` with prompt |
| Cold complete pipeline | 70.3 s total before response bounding |
| Warm complete pipeline, Qwen on GPU | 21.0 s total: STT 9.14 s, LLM 7.06 s, TTS 4.77 s |
| Bounded response duration | 4.19 s |
| Post-run memory | 6.3/7.4 GiB RAM, 2.0/3.7 GiB swap |
| Post-run temperature | GPU 54.0 C, junction 54.3 C |
| Deployed mDNS HTTP pipeline | 15.54 s HTTP; STT 5.07 s, LLM 6.53 s, TTS 3.69 s |
| Deployed response | HTTP 200, valid 16 kHz mono PCM16, 4.02 s audio |
| Malformed WAV | Structured HTTP 400; service remained active |

The active VS Code/desktop workload materially increased memory pressure and
STT process startup time. Repeat cold/warm benchmarks after deploying the
headless service. A CUDA Whisper attempt failed with `cudaMalloc` on a 140.5 MiB
allocation; this failure is recorded rather than reported as a passing GPU test.

### LAN name

The validated Jetson advertises `hosaka-jetson.local` through Avahi only on
`wlP1p1s0` and `enP8p1s0`; Docker and USB bridge interfaces are excluded. The
Linux hostname remains unchanged. Validate from the Pi with:

```bash
getent hosts hosaka-jetson.local
curl --fail http://hosaka-jetson.local:8421/health
```

The router should still reserve the Jetson addresses by MAC as a fallback.