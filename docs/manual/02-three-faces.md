# 02 · the three faces

Hosaka is one idea wearing three different bodies.

```
hosaka.xyz                 marketing       cyber_deck_website  → vercel
terminal.hosaka.xyz        hosted console  hosaka_field-terminal → vercel + fly.io
hosaka pi @ :8421          appliance       hosaka_console/Hosaka → raspberry pi
                                                ▲
                          you, this Mac, ──────┘  via hosakactl
```

The shape:

```
    your laptop
        │  git push
        ▼
   ┌──────────────┐
   │   GitHub     │  source of truth
   └──────┬───────┘
          │  webhook on push to main
          ▼
   ┌──────────────┐    /api/gemini  (edge function)
   │   Vercel     │ ── proxy for the /ask command
   │              │    holds GEMINI_API_KEY
   │  serves the  │
   │  static SPA  │    browser ── wss://… ──┐
   └──────────────┘                         │
                                            ▼
                                     ┌──────────────┐
                                     │   Fly.io     │  picoclaw box
                                     │              │  the heartbeat
                                     │  agent-server│  holds
                                     │  + picoclaw  │  GEMINI/OPENAI key
                                     └──────────────┘  + HOSAKA_ACCESS_TOKEN
```

---

## face 1 — the hosted terminal

**URL:** `terminal.hosaka.xyz`
**Lives on:** Vercel (frontend + edge proxy) + Fly.io (agent backend)
**You need:** a browser. That's it. Maybe the magic word.

This is the public-facing version of Hosaka. A static React SPA served
by Vercel, which talks to:

- **Vercel Edge Function** (`/api/gemini`) for one-shot LLM questions
  via the `/ask` command. The Gemini API key never touches your browser.
- **Fly.io picoclaw bridge** (`wss://agent.hosaka.app/ws/agent`) for
  the full agent — the thing that walks a sandboxed filesystem and
  runs `!` shell commands.

It opens with the agent channel **closed**. To open it, you say the
word. (See [opening the channel](05-the-hosted-terminal/02-opening-the-channel.md).)

→ Full chapter: [05 · the hosted terminal](05-the-hosted-terminal/README.md)

---

## face 2 — the appliance

**Where:** a Raspberry Pi (3B+ or newer) with a touchscreen.
**Port:** `:8421` on whatever IP the Pi gets.
**You need:** a Pi, an SD card, an SSH session, ten minutes.

This is the _real_ Hosaka. The full Python TUI (`python -m hosaka`)
running on a real device, plus the same React frontend served as a
local kiosk on the touchscreen. It runs on systemd as a set of
services:

- `hosaka-webserver.service` — the FastAPI server on `:8421`
- `picoclaw-gateway.service` — the agent runtime
- `hosaka-mode.service` — switches between console (kiosk) and device modes
- `hosaka-device-dashboard.service` — the TTY dashboard you see on
  HDMI when the kiosk is off

Once it's installed, an operator drives it three ways:

1. **The touchscreen** — tap the dock, switch tabs, type into the terminal.
2. **A web browser on the LAN** — point any device at `http://<pi-ip>:8421`.
3. **`hosakactl` on a laptop** — see face 3.

→ Full chapter: [06 · the appliance](06-the-appliance/README.md)

---

## face 3 — the laptop client (hosakactl)

**What:** a single-file Python script (stdlib only).
**Where:** `/usr/local/bin/hosakactl` on your laptop.
**You need:** Python 3.9+ (macOS already has it).

`hosakactl` is how you talk to a remote Pi without SSHing into it. It
hits the appliance's `/api/v1/*` endpoints with a bearer token and
gives you a tidy CLI for status, mode toggles, wifi, and unit
restarts. It also works against the Docker version on your localhost.

```bash
hosakactl link http://hosaka.local:8421       # one-time, paste token
hosakactl status                              # full snapshot
hosakactl mode device --persist -y            # ssh-friendly mode
hosakactl wifi add "Cafe Free WiFi"           # add a network remotely
```

→ Full chapter: [07 · the laptop client (hosakactl)](07-the-laptop-client/README.md)

---

## bonus face — docker

If you don't have a Pi but want to run the full stack, there's a
docker compose setup that gives you the appliance experience on your
Mac. Same Python package, same `:8421`, same `hosakactl` workflow.

→ Chapter: [08 · the docker edition](08-the-docker-edition.md)

---

## which one should you start with?

| You have… | Start here |
|---|---|
| only a browser | [05 · the hosted terminal](05-the-hosted-terminal/README.md) |
| a Pi on hand | [06 · the appliance](06-the-appliance/README.md) |
| a Mac and Docker | [08 · the docker edition](08-the-docker-edition.md) |
| a Pi and a Mac and curiosity | start with the Pi, then [hosakactl](07-the-laptop-client/README.md) |
| an afternoon and no plan | [03 · quickstart](03-quickstart.md) |

> _signal steady. no wrong way._
