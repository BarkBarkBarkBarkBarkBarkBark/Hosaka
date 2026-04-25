# Hosaka

> Field-terminal Raspberry Pi running a FastAPI backend, a React kiosk SPA, and
> a small operator CLI. This site is the single source of truth for the public
> API and the `hosakactl` laptop client.

## What this is

| | |
|---|---|
| **Hardware** | Raspberry Pi 3B / 4 / Zero 2 W with a small touchscreen |
| **Backend** | `hosaka/web/server.py` — FastAPI, port `8421` |
| **Frontend** | `frontend/` — Vite + React, served from `/` |
| **Operator CLI** | `/usr/local/bin/hosaka` (on the Pi) |
| **Laptop client** | [`hosakactl`](client.md) (Mac / Linux, stdlib only) |
| **API contract** | [`/api/v1/*`](api.md) — versioned, OpenAPI-described |

## Two operating modes

Hosaka boots in one of two modes. They are documented in detail under
[Modes](modes.md). Quick version:

- **console** — the default. Touchscreen kiosk + terminal + reading panel.
- **device** — the diagnostic mode. Kiosk down, picoclaw paused, TTY1 shows a
  live dashboard (IP, ports, RAM, battery), and `hosakactl` / `/device` are the
  way you interact with the box.

Switching modes is one of:

```bash
# On the Pi
hosaka mode device --persist

# From your laptop
hosakactl mode device --persist
```

…or the **switch to device / switch to console** button in the kiosk header
(opens a confirm dialog first).

## Where to start

1. [Quickstart](quickstart.md) — install on a Pi, generate the API token,
   point `hosakactl` at it from your laptop.
2. [API reference](api.md) — the `/api/v1/*` surface, rendered live from the
   FastAPI OpenAPI schema.
3. [Wifi setup](wifi.md) — multiple ways to add a network (kiosk UI, `/device`
   page, `hosakactl wifi add`, TTY hotkey).
4. [Beacon protocol](beacon_protocol.md) — how Hosaka nodes advertise
   presence, commit, and capability metadata on the tailnet.
5. [Inbox / notifications](inbox_notifications.md) — append-only operator
   notices and acknowledgements, with optional peer gossip.
6. [Local bridge + gateway implementation](local_bridge_gateway.md) — how to
   add a safe localhost handoff bridge, which keys you need, and how to verify
   the Docker runtime before you expose anything.
7. [HTTP GET / POST surface](http_surface.md) — allowlisted outbound HTTP for
   agent/operator workflows.
8. [Claims audit](claims.md) — what this codebase actually does vs. what older
   docs claimed it did.
