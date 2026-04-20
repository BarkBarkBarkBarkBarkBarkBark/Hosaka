# 04 · accounts you'll need

Hosaka is _mostly_ self-contained. But to make the AI bits work, and to
host your own copy, you'll touch a small constellation of platforms.

| Platform | Why you'd want one | When to skip |
|---|---|---|
| **Google AI Studio** (Gemini) | the cheapest LLM keys; what the hosted version uses | if you're using OpenAI |
| **OpenAI** | optional — for `gpt-4o-mini` etc. | if Gemini is enough |
| **GitHub** | source of truth, GH Pages for this manual, CI | required to host your own |
| **Vercel** | serves the static SPA + the `/api/gemini` edge proxy | if you're not hosting `terminal.hosaka.xyz` |
| **Fly.io** | hosts the picoclaw agent at `agent.hosaka.app` | if you're not hosting your own agent |
| **Tailscale** | overlay network so you can reach your Pi from anywhere | if your Pi is on the same LAN as you forever |

Below: the bare minimum for each.

---

## google ai studio (gemini)

The cheapest path to a working LLM key. Free tier exists.

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Click **Create API key**. Pick a project (any).
3. Copy the key. It looks like `AIza…`.
4. Where it goes:
   - **Hosted (`terminal.hosaka.xyz`):** as `GEMINI_API_KEY` in Vercel
     env vars _and_ as a Fly secret on the agent server (see below).
   - **Appliance:** in `/opt/hosaka/.env` as `GEMINI_API_KEY=AIza…`,
     or in `~/.picoclaw/config.json` per the picoclaw config.
   - **Docker:** in the project's `.env` file as `GEMINI_API_KEY=…`.

> The browser **never** holds the key. Every model call is brokered by
> Vercel (`/api/gemini`) or Fly (picoclaw) using server-side secrets.

---

## openai (optional)

If you want `gpt-4o-mini` instead of Gemini.

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. **Create new secret key.** Copy it. Looks like `sk-…`.
3. Where it goes — same idea as Gemini, but as `OPENAI_API_KEY`.
4. On the Pi, also set `PICOCLAW_MODEL=openai/gpt-4o-mini` so picoclaw
   picks the OpenAI router at startup.

The agent server's `start.sh` picks the **first** of `GEMINI_API_KEY` /
`OPENAI_API_KEY` it finds in the environment. So to switch providers,
unset one and set the other:

```bash
fly secrets unset GEMINI_API_KEY
fly secrets set OPENAI_API_KEY=sk-… PICOCLAW_MODEL=openai/gpt-4o-mini
fly deploy --no-cache
```

---

## github

You need an account if you want to:

- fork Hosaka and customize it
- deploy this manual to GitHub Pages
- ship updates to your own Vercel deployment via push-to-main

No special config beyond the usual SSH key + `gh auth login`.

---

## vercel

Hosts the static SPA at `terminal.hosaka.xyz` (or your own subdomain)
and runs the edge proxy at `/api/gemini`.

Setup:

```bash
npm i -g vercel
cd ~/Cursor_Folder/Cursor_Codespace/hosaka_field-terminal
vercel link    # follow prompts
```

Required env vars (set in **Project → Settings → Environment Variables**):

| Variable | Example | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `AIza…` | server-side, used by `api/gemini.ts` for `/ask` |
| `VITE_SHOW_SETTINGS` | `1` | shows the ⚙ icon in the header |
| `VITE_HOSAKA_AGENT_URL` | `wss://agent.hosaka.app/ws/agent` | where the agent lives |
| `VITE_HOSAKA_MAGIC_WORD` | `neuro` | the passphrase that opens the channel |

Push to `main` redeploys.

---

## fly.io

Hosts the picoclaw agent — a FastAPI WebSocket server that wraps
picoclaw inside a sandboxed workspace.

Setup:

```bash
cd ~/Cursor_Folder/Cursor_Codespace/hosaka_field-terminal
fly launch    # uses the repo's Dockerfile + fly.toml
```

Required secrets:

```bash
fly secrets set HOSAKA_ACCESS_TOKEN='neuro'                 # MUST equal VITE_HOSAKA_MAGIC_WORD
fly secrets set GEMINI_API_KEY='AIza…'                      # or OPENAI_API_KEY
fly secrets set HOSAKA_ALLOWED_ORIGINS='https://terminal.hosaka.xyz'
fly secrets set PICOCLAW_MODEL='gemini/gemini-2.5-flash-lite'  # optional override
fly deploy
```

The **`HOSAKA_ACCESS_TOKEN` must equal the `VITE_HOSAKA_MAGIC_WORD`**
the frontend ships with. They are the same word, on two sides of a door.

---

## tailscale (optional, recommended)

If you want to reach your Pi from a coffee shop without port-forwarding:

1. Sign up at [tailscale.com](https://tailscale.com).
2. Install on the Pi: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`.
3. Install on your laptop: same.
4. Both devices show up in `tailscale status`. Use the `100.x.y.z`
   tailnet IP (or the magic dns name like `hosaka.tail-scale.ts.net`)
   in `hosakactl link`.

This lets you run `hosakactl status` from anywhere, encrypted, no
port-forward, no VPN.

---

## summary — bare minimum to play

| Goal | What you need |
|---|---|
| Use the hosted terminal | nothing. just a browser. |
| Self-host the hosted terminal | GitHub + Vercel + Fly.io + a Gemini or OpenAI key |
| Run the appliance on a Pi | a Pi + a Gemini or OpenAI key (optional, only for `/ask`) |
| Drive the appliance from your laptop | the Pi above + Python on your laptop |

> _the orb does not need credentials. it has always been here._
