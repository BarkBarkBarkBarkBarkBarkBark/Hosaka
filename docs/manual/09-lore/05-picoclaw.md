# 09.05 · picoclaw

> _picoclaw is the brains of operation —_
> _a lightweight local agent binary._
> _everything typed at the `hosaka>` prompt goes straight to picoclaw._
> _— the no-wrong-way manifest_

Picoclaw is the agent runtime. The thing that does the actual thinking
in Hosaka. Without picoclaw, you have a cool ASCII terminal and an
alien plant. With picoclaw, you have an agent with hands.

---

## what picoclaw is, technically

Picoclaw is a single Linux binary from
[`sipeed/picoclaw`](https://github.com/sipeed/picoclaw) that runs an
agent loop locally:

- Listens on a Unix socket / TCP gateway (`:18790` by convention).
- Maintains a sandboxed workspace (a chroot-like jail).
- Routes requests through configured model providers (Gemini, OpenAI, etc.).
- Exposes tools (read, write, walk, run).
- Persists session state.

Hosaka talks to picoclaw via the `picoclaw-gateway.service` systemd
unit on the appliance, and via `wss://agent.hosaka.app/ws/agent` on
the hosted side.

---

## install (Pi)

```bash
cd /tmp
curl -L https://github.com/sipeed/picoclaw/releases/download/v0.2.4/picoclaw_Linux_arm64.tar.gz \
  -o picoclaw.tar.gz
tar -xzf picoclaw.tar.gz && chmod +x picoclaw && sudo mv picoclaw /usr/local/bin/
picoclaw onboard
```

Then point at a model in `~/.picoclaw/config.json`:

```json
{
  "model_list": [
    {
      "model_name": "gpt-4o-mini",
      "model": "openai/gpt-4o-mini",
      "api_key": "sk-…",
      "api_base": "https://api.openai.com/v1"
    }
  ]
}
```

Or for Gemini: `"model": "gemini/gemini-2.5-flash-lite"`.

---

## how Hosaka wires to it

The appliance wires picoclaw via env vars (typically in `/opt/hosaka/.env`):

| Var | Default | Purpose |
|---|---|---|
| `PICOCLAW_GATEWAY_URL` | `ws://127.0.0.1:18790` | where the gateway listens |
| `PICOCLAW_GATEWAY_TOKEN` | (optional) | gateway auth |
| `PICOCLAW_GATEWAY_PASSWORD` | (optional) | gateway password |
| `PICOCLAW_SESSION` | `hosaka:main` | session key |
| `PICOCLAW_MODEL` | (default) | override the model |

The Hosaka python TUI talks to picoclaw via the subprocess adapter.
The web frontend (on the hosted side) talks to a separate agent server
on Fly.io that wraps picoclaw inside a FastAPI WebSocket.

---

## picoclaw's flag commands

```
picoclaw onboard         # one-time setup
picoclaw auth weixin     # login flows
picoclaw auth login      # login flows
picoclaw agent           # start the agent loop directly
picoclaw gateway         # start the gateway daemon
picoclaw status          # show running picoclaw processes / sockets
picoclaw version
picoclaw model           # show or set the active model
picoclaw cron *          # scheduled tasks
picoclaw skills *        # skill management
picoclaw migrate         # state migrations
```

Hosaka uses `picoclaw gateway` (run by `picoclaw-gateway.service`) and
the agent adapter under the hood. You don't typically call picoclaw
directly.

---

## diagnosing picoclaw from inside Hosaka

```
/picoclaw                # subcommand entry
/picoclaw status         # is it running?
/picoclaw doctor         # what's wrong?
/doctor                  # full system diagnose, includes picoclaw
```

If `/picoclaw doctor` flags an issue, the most likely culprits:

- empty / invalid `api_key` in `~/.picoclaw/config.json`
- gateway not running (`sudo systemctl restart picoclaw-gateway.service`)
- model name is unknown or unauthorized for the active key
- in device mode, picoclaw is intentionally **off** (see [boot modes](../06-the-appliance/04-boot-modes.md))

---

## the lore of picoclaw

The library doesn't directly describe picoclaw — it predates the
hosted Hosaka. In-system, picoclaw is the **mechanism by which the
orb makes contact**. The orb is the voice; picoclaw is the hands.

When you see in the terminal:

```
... picoclaw walks the directory ...
... speaking with picoclaw ...
```

…that's a window into picoclaw doing the work the orb is too dignified
to mention. (Picoclaw walks. The orb watches.)

---

## tools picoclaw has, in the sandbox

When the channel is open on the hosted edition, picoclaw has these
verbs available:

- **walk** the workspace (`!ls`, `!find`)
- **read** files (`!cat`)
- **write** files (`echo … > file.txt`)
- **run** shell commands (`shlex.split` + denylist for safety)
- **probe** the network (limited; powers `[REAL]` lines in `/netscan`)

On the appliance, the sandbox is the host shell — there is no chroot,
because the agent is _supposed_ to be able to manage the device.

---

## why picoclaw and not just "openai client"

Because picoclaw is **provider-agnostic** and runs locally. It:

- abstracts over Gemini, OpenAI, Anthropic, Ollama, etc.
- holds tool definitions and conversation state without burning
  tokens on rebuilding context every turn
- runs on tiny ARM hardware
- exposes a stable socket the rest of Hosaka can bind to

Hosaka is, structurally, a **shell on top of picoclaw**. Picoclaw is
the agent. Hosaka is the room the agent lives in.

> _signal steady._
