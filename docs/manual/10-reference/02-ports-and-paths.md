# 10.02 · ports & paths

Where things listen, where things write, where things live.

---

## ports

| Port | Surface | Where |
|---|---|---|
| `8421` | Hosaka webserver (FastAPI) | the appliance + the docker container |
| `18790` | picoclaw gateway (in-process) | the appliance + the docker container |
| `5173` | vite dev server | only when running `npm run dev` locally |
| `4000` | jekyll dev server | only when running this manual locally |
| `443` | hosted SPA + edge proxy | `terminal.hosaka.xyz` (Vercel) |
| `443` | agent WS | `agent.hosaka.app` (Fly.io) |

---

## the appliance filesystem

| Path | Purpose | Notes |
|---|---|---|
| `/usr/local/bin/hosaka` | operator CLI | installed by `install_hosaka.sh` |
| `/usr/local/bin/hosakactl` | (also) the client itself if you copied it here | optional; same script that runs on your laptop |
| `/usr/local/bin/picoclaw` | the picoclaw binary | installed manually |
| `/etc/hosaka/api-token` | bearer token | mode `640`, group `hosaka` |
| `/etc/systemd/system/hosaka-*.service` | systemd units | created by installer |
| `/opt/hosaka/.env` | env file for the webserver / TUI | edit + `systemctl restart` |
| `/opt/hosaka-field-terminal/` | deploy target | from `hosaka deploy` |
| `/var/lib/hosaka/mode` | current mode marker | `console` or `device` |
| `/boot/firmware/hosaka-build-mode` | persistent boot-mode marker | written by `--persist` |
| `~/.hosaka/state.json` | TUI state (todos, history, etc.) | per-user |
| `~/.hosaka/plant.json` | plant vitality + birth log | per-user |
| `~/.picoclaw/config.json` | picoclaw model config | edit, `picoclaw onboard` |
| `~/Hosaka/` | source checkout (after `git clone`) | optional; for development |

---

## the laptop / hosakactl filesystem

| Path | Purpose |
|---|---|
| `/usr/local/bin/hosakactl` | the script |
| `~/.hosaka/client.json` | host + token (mode `0600`) |

---

## the hosted SPA paths

| Path | What |
|---|---|
| `/` | the SPA |
| `/api/gemini` | Vercel Edge proxy for the `/ask` command |
| `/library/index.json` | library index, served by the SPA |
| `/library/<slug>.md` | library fragments |
| `/locales/<lang>/<ns>.json` | i18n strings |
| `/api/video/next` | (appliance) next video in the loop |

---

## the agent server paths (Fly.io)

| Path | What |
|---|---|
| `/health` | health check (`fly status` + healthchecks) |
| `/ws/agent` | the agent WebSocket (gated by `HOSAKA_ACCESS_TOKEN`) |

---

## the API on the appliance

See [03 · the API](03-api.md) for the full list. Quick map:

```
/api/v1/health           GET
/api/v1/system/info      GET
/api/v1/mode             GET, POST
/api/v1/wifi             GET, POST, DELETE
/api/v1/services         GET
/api/v1/services/<unit>/restart  POST
```

All loopback. From LAN, reads open / writes need bearer token.

---

## the systemd units

| Unit | What it does |
|---|---|
| `hosaka-webserver.service` | FastAPI app on `:8421` |
| `picoclaw-gateway.service` | picoclaw gateway daemon on `:18790` |
| `hosaka-mode.service` | runs at boot to set the right mode (console / device) |
| `hosaka-device-dashboard.service` | TTY dashboard (only when in device mode) |

```bash
sudo systemctl status hosaka-webserver.service
sudo systemctl restart picoclaw-gateway.service
sudo journalctl -u hosaka-mode.service -e
```
