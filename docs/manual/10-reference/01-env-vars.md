# 10.01 · environment variables

Everything Hosaka reads from the environment, grouped by where it's read.

---

## the appliance (`hosaka` python TUI + webserver)

Set in `/opt/hosaka/.env` (or any systemd `EnvironmentFile`).

| Var | Default | What |
|---|---|---|
| `HOSAKA_BOOT_MODE` | `console` | `console` (TUI + kiosk), `headless` / `web` (API+SPA only), `kiosk` (touchscreen only, no TUI on tty) |
| `HOSAKA_STATE_PATH` | `~/.hosaka/state.json` | persistent state (todos, plant on appliance) |
| `HOSAKA_WEB_HOST` | `0.0.0.0` | bind interface for the webserver |
| `HOSAKA_WEB_PORT` | `8421` | port |
| `HOSAKA_SOURCEMAP` | unset | set to `1` to emit sourcemaps from `vite build` (off by default to halve the build's RAM peak) |
| `HOSAKA_DEPLOY` | `/opt/hosaka-field-terminal` | rsync target for `hosaka deploy` |

---

## picoclaw

| Var | Default | What |
|---|---|---|
| `PICOCLAW_GATEWAY_URL` | `ws://127.0.0.1:18790` | where Hosaka talks to the picoclaw gateway |
| `PICOCLAW_GATEWAY_TOKEN` | (unset) | optional auth token for the gateway |
| `PICOCLAW_GATEWAY_PASSWORD` | (unset) | optional password |
| `PICOCLAW_SESSION` | `hosaka:main` | session key |
| `PICOCLAW_MODEL` | (default in config) | override the active model |

Picoclaw also reads `~/.picoclaw/config.json` directly for `model_list`,
api keys, etc.

---

## the model providers

| Var | Used by | What |
|---|---|---|
| `OPENAI_API_KEY` | picoclaw, agent-server | OpenAI key (`sk-…`) |
| `GEMINI_API_KEY` | Vercel `api/gemini.ts`, picoclaw, agent-server | Gemini key (`AIza…`) |

The agent-server's `start.sh` picks the **first** of `GEMINI_API_KEY` /
`OPENAI_API_KEY` it finds at boot.

---

## the hosted SPA (build-time, `VITE_*`)

These are baked into the static build at `npm run build` time.

| Var | Default | What |
|---|---|---|
| `VITE_HOSAKA_AGENT_URL` | `wss://hosaka-field-terminal-alpha.fly.dev/ws/agent` | where the picoclaw agent lives |
| `VITE_HOSAKA_MAGIC_WORD` | `neuro` | the passphrase that opens the channel |
| `VITE_HOSAKA_API_BASE` | (empty / same-origin) | base for `/api/gemini` if hosted off-origin |
| `VITE_SHOW_SETTINGS` | `0` | set to `1` to show the ⚙ icon in the header |

---

## the Vercel deployment (`hosaka_field-terminal`)

Set in **Vercel → Project → Settings → Environment Variables**.

| Var | What |
|---|---|
| `GEMINI_API_KEY` | server-side, used by `api/gemini.ts` for `/ask` |
| `VITE_SHOW_SETTINGS` | `1` to show the cog |
| `VITE_HOSAKA_AGENT_URL` | `wss://agent.hosaka.app/ws/agent` |
| `VITE_HOSAKA_MAGIC_WORD` | the magic word |
| `AMAZON_PA_ACCESS_KEY` | Amazon PA-API access key (enables `/books` relay) |
| `AMAZON_PA_SECRET_KEY` | Amazon PA-API secret key |
| `AMAZON_PA_PARTNER_TAG` | Amazon Associates partner tag (e.g. `hosaka-20`) |
| `AMAZON_PA_REGION` | PA-API region, default `us-east-1` |

The Amazon PA-API vars are **optional**. If absent, the Books panel shows a
"not wired up yet" message and degrades gracefully.

Plus any Vercel-managed config (build commands, output dir, etc.) in
`vercel.json`.

---

## the Fly.io deployment (`agent-server`)

Set with `fly secrets set …`.

| Secret | What |
|---|---|
| `HOSAKA_ACCESS_TOKEN` | **must equal** `VITE_HOSAKA_MAGIC_WORD` |
| `GEMINI_API_KEY` | the Gemini key (or…) |
| `OPENAI_API_KEY` | …the OpenAI key |
| `PICOCLAW_MODEL` | optional override (e.g. `gemini/gemini-2.5-flash-lite`) |
| `HOSAKA_ALLOWED_ORIGINS` | CSV; e.g. `https://terminal.hosaka.xyz` |

---

## the laptop client (`hosakactl`)

| Var | Default | What |
|---|---|---|
| `HOSAKA_HOST` | from `~/.hosaka/client.json` | override the host per call |
| `HOSAKA_TOKEN` | from `~/.hosaka/client.json` | override the token per call |
| `HOSAKACTL_CONFIG` | `~/.hosaka/client.json` | use a different config file |

---

## quick recipes

```bash
# point hosakactl at a different Pi, one shot
HOSAKA_HOST=http://192.168.1.55:8421 HOSAKA_TOKEN=xxx hosakactl status

# enable the cog in the SPA build
VITE_SHOW_SETTINGS=1 npm run build

# run the SPA pointing at a different agent for testing
VITE_HOSAKA_AGENT_URL=wss://staging-agent.fly.dev/ws/agent npm run build
```
