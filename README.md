# Hosaka Field Terminal

```
  ██╗  ██╗ ██████╗ ███████╗ █████╗ ██╗  ██╗ █████╗
  ██║  ██║██╔═══██╗██╔════╝██╔══██╗██║ ██╔╝██╔══██╗
  ███████║██║   ██║███████╗███████║█████╔╝ ███████║
  ██╔══██║██║   ██║╚════██║██╔══██║██╔═██╗ ██╔══██║
  ██║  ██║╚██████╔╝███████║██║  ██║██║  ██╗██║  ██║
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝

      * \ _ /
       @( )@          A console-first AI field terminal.
      */\|/\*         Signal steady. No wrong way.
     (@)|  /\
      \ | /(_)
       _|_/_
      [_____]
```

An AI-powered appliance shell for cyberdecks and Raspberry Pis.
Type anything — it goes straight to the agent.
Use it enough and the plant blooms. Neglect it and it wilts.

There is no wrong way.

---

## Install in one line

**mac / linux**

```bash
curl -fsSL https://install.hosaka.xyz | sh
```

**windows (PowerShell)**

```powershell
iwr https://install.hosaka.xyz/windows | iex
```

Then:

```bash
hosaka up          # start the local node (web UI on http://127.0.0.1:8421)
hosaka tui         # drop into the console TUI
hosaka open        # open the web UI in your browser
hosaka link HOST   # route this client at a remote hosaka on your tailnet
hosaka help        # see everything
```

Requires [Docker](https://www.docker.com/products/docker-desktop).
See [`install/`](./install/) for the installer internals.

---

## The single entrypoint

The canonical way to run Hosaka — on the Pi, on your laptop, anywhere —
is the **Electron kiosk host** at [`kiosk/`](./kiosk/). It wraps the
SPA in a native Chromium window and turns on Electron's `<webview>` tag
so the Web panel renders any URL inline, with no X-Frame-Options grief.

```bash
cd kiosk
npm install      # first time only
npm run dev      # vite + electron together, HMR, windowed
```

On the edge device, `hosaka-kiosk.service` runs the same Electron host
fullscreen at boot, pointed at the local FastAPI on `127.0.0.1:8421`.
See [`kiosk/README.md`](./kiosk/README.md) for details.

---

## Documentation

Full reference site (auto-built from this commit on every push to `main`):

**→ https://&lt;your-gh-user&gt;.github.io/Hosaka/**

What lives there:

- **API reference** — the live `/api/v1/*` OpenAPI spec, rendered via Swagger UI.
- **`hosakactl`** — the single-file laptop client that talks to that API.
- **Modes** — what `console` / `device` actually do under the hood.
- **Wifi setup** — every way to add a network (kiosk button, `/device` page,
  `hosakactl wifi add`, TTY hotkey).
- **Claims audit** — what the codebase actually does vs. what older docs claim.

Build it locally:

```bash
pip install -r docs/requirements.txt
python scripts/dump_openapi.py docs/openapi.json
mkdocs serve              # http://127.0.0.1:8000
```

## Remote configuration from your laptop

After `install_hosaka_lean.sh` runs on the Pi it generates
`/etc/hosaka/api-token` (group-readable by the operator). Drop the
single-file client on your laptop:

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/Hosaka/main/scripts/hosakactl \
  -o /usr/local/bin/hosakactl && chmod +x /usr/local/bin/hosakactl

hosakactl link http://hosaka.local:8421       # prompts for token
hosakactl status                              # full snapshot
hosakactl mode device --persist -y            # SSH-friendly
hosakactl wifi add "Cafe Free WiFi"           # prompts for password
hosakactl test                                # smoke-test all endpoints
```

Stdlib only, no install. Works on Mac, Linux, and the Pi itself.

---

## Install

### 1. Install Picoclaw

```bash
cd /tmp
curl -L https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz \
  -o picoclaw.tar.gz
tar -xzf picoclaw.tar.gz && chmod +x picoclaw && sudo mv picoclaw /usr/local/bin/
picoclaw onboard
```

### 2. Configure your LLM backend

Hosted Docker users (the common case) can skip manual config — Hosaka
prompts you automatically:

- **Inline shell prompt**: type anything in the terminal on first launch
  and the shell asks:
  ```
    no llm backend configured.
    configure one now? [Y/n]
  ```
  Walks you through provider, model, base URL (for local/Ollama), and
  API key (input is masked — never logged or sent as chat context).

- **Settings drawer**: click the ⚙ gear icon anytime → **LLM Backend**
  section. Supports OpenAI and any OpenAI-compatible endpoint (Ollama,
  LM Studio, etc.). Your API key is stored on the server in
  `/var/lib/hosaka/llm.json` and applied to the running process
  immediately — no restart required.

- **Environment variables** (appliance / advanced):
  ```bash
  export OPENAI_API_KEY=sk-...
  export OPENAI_MODEL=gpt-4o-mini            # optional, default
  export OPENAI_BASE_URL=http://localhost:11434/v1  # for Ollama etc.
  ```

Any of these approaches works — mix and match.

> **Privacy**: the API key is stored on-device only. It is never sent
> to Hosaka's servers, never logged, and never included in chat context.

### 3. Clone and run

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/Hosaka.git
cd Hosaka
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-hosaka.txt
picoclaw gateway &
python -m hosaka
```

### 4. Appliance install (Raspberry Pi)

```bash
./scripts/setup_hosaka.sh
```

One command. Installs everything, enables systemd services, starts onboarding.

After install you'll have a `hosaka` command on the path — see "Operator CLI"
below for the build/kiosk mode toggle and one-shot deploys.

---

## Operator CLI

Once installed, the Pi exposes a `hosaka` command for day-to-day operations:

```bash
hosaka status                  # what's running, RAM/CPU snapshot, current mode
hosaka mode build [--persist]  # stop kiosk, free RAM/CPU for SSH workflows
hosaka mode kiosk [--persist]  # restore the touchscreen kiosk
hosaka build [--check]         # cd frontend && npm run build (--check runs tsc gate)
hosaka deploy [--check]        # build + rsync into /opt + restart webserver
hosaka logs [web|pico|<unit>]  # tail journalctl
hosaka reboot                  # safe sync + reboot
```

### Why "build mode"?

The Pi 3B has **906 MiB RAM**. With Chromium kiosk + uvicorn + picoclaw +
the Cursor remote server all loaded, there is no headroom left for
`npm run build` and the OOM killer takes the build (or, worse, the SSH
session). `hosaka mode build` shuts down the kiosk and the picoclaw gateway
to free ~700 MiB before you build. `--persist` writes a marker to
`/boot/firmware/hosaka-build-mode` so the Pi stays in build mode across
reboots until you flip back with `hosaka mode kiosk --persist`.

A typical SSH-then-deploy session looks like:

```bash
ssh operator@hosaka
hosaka mode build
cd ~/Hosaka && git pull
hosaka deploy
hosaka mode kiosk
```

### Why is the build so much lighter now?

We aggressively stripped the frontend in 2026-04 (see
`.cursor/plans/hosaka_lean_&_build_mode_*.plan.md`):

- `tsc -b` is no longer in the default build path — `npm run build` is just
  `vite build` (~250 MB peak vs. ~750 MB before). Use `npm run build:check`
  on a dev machine for the type-safety gate.
- Sourcemaps off by default (`HOSAKA_SOURCEMAP=1` to re-enable).
- All panels are `React.lazy`'d so first paint is just the shell.
- `react-markdown` + `remark-gfm` (~1 MB of `node_modules`, 15 transitive
  deps) replaced with `marked` (~50 KB, zero deps).
- The whole `i18next` + `react-i18next` + http-backend + language-detector
  stack (~2 MB) replaced with a 200-line in-house hook in
  [`frontend/src/i18n.ts`](frontend/src/i18n.ts) that bundles all 6 locales
  via `import.meta.glob`.

Net bundle: **~4.8 MB → ~700 KB**. Build memory peak: **~750 MB → ~250 MB**.

---

## Docker (no Pi required)

```bash
./docker/dev.sh               # start services
./docker/dev.sh tui            # full interactive terminal
./docker/dev.sh test           # run tests
./docker/dev.sh stop           # shut down
```

---

## What you get

```
hosaka:/home/operator > /commands

  ── Chat & AI ──
    /chat              Interactive AI session
    /ask <text>        One-shot question

  ── System ──
    /status            Uptime, IP, model, services
    /doctor            Diagnose config
    /restart all       Restart services
    /update            Pull + redeploy

  ── Network ──
    /net               IP, Wi-Fi, Tailscale
    /ping /dns /scan   Network tools

  ── Tools ──
    /draw <subject>    AI-generated ASCII art
    /plant             Check on your alien plant
    /orb               The orb sees you
    /code              Drop to shell

  ── Reference ──
    /help              Quick start
    /lore              ...
    /about             System info
```

Everything else you type goes to the AI agent. Prefix `!` for shell commands.

---

## The plant

An alien organism lives in your terminal. It grows when you use Hosaka
and wilts when you don't.

```
  dead        wilted       dry        stable      growing      bloom       colony

              ,            \ |         _         \ _ /       * \ _ /     *@* _ *@*
              |\            \|        ( )        -( )-        @( )@      \@(*)@/ *
   .          | )            |        \|/       / \|         */\|/\*    */\\|//\@*
   |          |/             |         |       (_) |/\      (@)|  /\    (@)|  /\(@
   |         _|_           __|__     __|__         |/        \ | /(_)    *\|*/(_)*
  .|.       [___]         [_____]   [_____]      __|__        _|_/_      __|_/__|_
 [___]                                          [_____]      [_____]    [___][__]
```

State persists to `~/.hosaka/plant.json`. Every command feeds it.
Hours of inactivity drain it. Reach colony state and it records a birth.


---

## Voice mode

Talk to Hosaka. Wake word + OpenAI Realtime + a webcam for the `see()`
tool. Runs in two places:

- **Kiosk panel** — tap the `◎ voice` tab, hit the orb, say something.
  Uses browser `getUserMedia` + WebRTC to OpenAI; the API key never
  leaves the Pi (the backend mints a short-lived session token).
- **Headless daemon** — `hosaka voice` (or the `hosaka-voice.service`
  unit). Runs across the room with a USB mic/speaker; default wake
  word is "hey jarvis" because that model is bundled with
  openwakeword. A custom "hey hosaka" needs training — see
  [openwakeword docs](https://github.com/dscripka/openWakeWord#training-new-models).

### Install

```bash
./scripts/install_voice_deps.sh     # apt: portaudio, alsa, v4l, ffmpeg
                                    # pip: sounddevice, openwakeword, opencv, ...
export OPENAI_API_KEY=sk-...        # or put in /etc/hosaka/env
```

### Run

```bash
hosaka voice                         # foreground daemon
# or inside the Hosaka console:
/voice

# or as a systemd unit on the appliance:
sudo cp systemd/hosaka-voice.service /etc/systemd/system/
sudo systemctl enable --now hosaka-voice
```

### Tools exposed to the voice

The Realtime session has five tools it can call mid-conversation.
Four are thin; the fifth hands off to the full agent:

| Tool         | What it does                                    |
|--------------|-------------------------------------------------|
| `todo_add`   | Appends to `~/.hosaka/voice_todos.jsonl` (the VoicePanel mirrors it into the Todo panel) |
| `set_mode`   | Switches console/device mode via `hosaka mode`  |
| `get_status` | One-line summary: host, uptime, free RAM, CPU C |
| `see`        | Grabs a JPEG, runs `gpt-4o-mini` vision, speaks the caption |
| `ask_agent`  | Routes to picoclaw for real agentic tool use (shell, git, files) |

If you say "what do you see" / "describe the room" the model calls
`see()`. If you say "run `ls -la`" / "what's the biggest file in my
home dir" it should say "on it" and hand off to `ask_agent`.

### Env knobs

| Variable                          | Default                    | Note |
|-----------------------------------|----------------------------|------|
| `OPENAI_API_KEY`                  | —                          | Reuses the one `openai_adapter.py` already picks up |
| `HOSAKA_VOICE_MODEL`              | `gpt-4o-realtime-preview`  | Whatever latest realtime SKU you pay for |
| `HOSAKA_VOICE_VOICE`              | `verse`                    | One of the Realtime voice presets |
| `HOSAKA_VOICE_WAKEWORD`           | `hey_jarvis`               | openwakeword preset or path to `.onnx` |
| `HOSAKA_VOICE_WAKE_THRESHOLD`     | `0.5`                      | 0-1 trigger confidence |
| `HOSAKA_VOICE_INPUT_DEVICE`       | system default             | sounddevice index or name (see `python -c "import sounddevice as sd;print(sd.query_devices())"`) |
| `HOSAKA_VOICE_OUTPUT_DEVICE`      | system default             | same, for the speaker |
| `HOSAKA_VOICE_CAMERA`             | `/dev/video0`              | V4L2 device path or numeric index |
| `HOSAKA_VOICE_VISION_MODEL`       | `gpt-4o-mini`              | For the `see()` tool |
| `HOSAKA_VOICE_TURN_TIMEOUT`       | `45`                       | Hard cap on one turn's mic time, seconds |

### Echo + half-duplex

We mute the microphone while Hosaka is speaking (the daemon's audio
callback gates the input queue; the browser relies on the standard
`echoCancellation: true` WebRTC constraint). This is the cheapest way
to prevent the wake word from firing on Hosaka's own voice. If you
want full-duplex (interrupt while it's talking), you need a real AEC —
`speexdsp-python` on Pi will work, patches welcome.

### Hardware notes

- A USB webcam with a built-in mic is the easiest wiring — the mic
  shows up as a separate ALSA card; set `HOSAKA_VOICE_INPUT_DEVICE`
  to that card's index.
- The Pi 3B's built-in audio jack is fine for output. Anything louder
  wants a USB speaker or a DAC.
- `picoclaw` is a *soft* dependency — `ask_agent` falls back to
  plain `gpt-4o-mini` chat when picoclaw isn't on the path.

---

## Configuration

### LLM backend

Set via the **⚙ Settings drawer → LLM Backend** in the web UI, or via
the **inline terminal prompt** on first keystroke, or via env vars:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for OpenAI (and most compatible endpoints) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `OPENAI_BASE_URL` | `https://api.openai.com` | Override for Ollama, LM Studio, etc. |

Persisted config lives in `/var/lib/hosaka/llm.json` (or
`~/.hosaka/llm.json` for non-root installs) and is applied on startup.
PATCH `/api/llm-key` applies it to the running process without restart.

### System settings

All of the following are editable at runtime in the **⚙ Settings
drawer → System** section, or via PATCH `/api/config`:

| Variable | Default | Description |
|---|---|---|
| `HOSAKA_STATE_PATH` | `~/.hosaka/state.json` | Persistent state |
| `HOSAKA_BOOT_MODE` | `console` | `console` (Python tty shell), `headless` / `web` (API+SPA only), `kiosk` (same + Electron fullscreen; use `./scripts/switch_boot_mode.sh`) |
| `HOSAKA_SOURCEMAP` | unset | Set to `1` to emit sourcemaps from `vite build` (off by default to halve the build's RAM peak on the Pi) |
| `HOSAKA_WEB_PORT` | `8421` | LAN setup web server port |
| `PICOCLAW_SESSION` | `hosaka:main` | Agent session key |
| `PICOCLAW_MODEL` | *(default)* | Override model |
| `HOSAKA_PUBLIC_MODE` | unset | Set to `1` / `true` / `yes` to hide the ⚙ settings drawer from all users. Intended for the **public web deployment** of this repo where strangers should not be able to reconfigure the LLM backend or system settings. When set, `/api/health` returns `settings_enabled: false`; the frontend reads this on mount and never renders the gear button or `SettingsDrawer`. The check is **server-side** — it cannot be bypassed from the browser. Local Docker installs should leave this unset (settings enabled by default). **Do not remove this flag** — it is the deliberate access control boundary between the operator-owned appliance and the public-facing hosted instance. |

---

## Requirements

- Python 3.10+
- Picoclaw v0.2+
- systemd (for appliance boot)
- No desktop environment needed
