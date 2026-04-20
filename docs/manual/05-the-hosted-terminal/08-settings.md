# 05.08 · the settings drawer

> _settings are managed by the operator on the hosted build._

The settings drawer is the only configuration surface in the browser.
It opens from the **⚙** icon in the header (visible only when
`VITE_SHOW_SETTINGS=1` is set at build time) or from the terminal:

```
/settings
```

Some hosted builds intentionally hide it and reply:

```
settings are managed by the operator on the hosted build.
try /agent, /model, or just type and the channel handles the rest.
```

---

## sections

### gemini (the `/ask` model)

| Field | Default | Notes |
|---|---|---|
| Model | `gemini-2.5-flash-lite` | what `/ask` uses |
| | | the API key lives in **Vercel env**, never in the browser |

You can change the model from the terminal too:

```
/model                            # show current
/model gemini-2.5-flash           # set
```

Available model names depend on what your operator's Gemini key has
access to.

### picoclaw agent

| Field | Default | Notes |
|---|---|---|
| Agent WS URL | `wss://agent.hosaka.app/ws/agent` | where picoclaw lives |
| Passphrase | (build-time magic word) | set with `/agent passphrase …` |
| Channel | off | toggle on / off; same as `/agent on` and `/agent off` |

The corresponding terminal commands:

```
/agent url wss://your-agent.fly.dev/ws/agent
/agent passphrase your-magic-word
/agent on
/agent test
```

> The picoclaw model is **locked server-side**. The browser cannot
> override it; the operator has to redeploy the Fly.io agent with a
> new `PICOCLAW_MODEL` secret.

### messages (optional)

| Field | What it does |
|---|---|
| Webhook URL | where Messages POSTs your text |
| Webhook kind | `discord` / `slack` / `generic` |

Leave blank to use offline orb chat only.

### appearance / locale

| Field | What it does |
|---|---|
| Language | switches all UI strings (6 locales bundled) |
| Theme | currently single theme: phosphor amber on black |

---

## persistence

Every setting lives in `localStorage`:

| Key | What |
|---|---|
| `hosaka.llm.v1` | model + last conversation id |
| `hosaka.agent.v1` | agent URL, passphrase, channel state |
| `hosaka.todo.v1` | open loops |
| `hosaka.messages.v1` | message history + webhook config |
| `hosaka.locale` | active language |

Clear `localStorage` and the tab forgets. The orb remembers anyway.

---

## what's not here

- API keys. Never. Browser doesn't get them.
- Picoclaw model. Operator-controlled, server-side.
- Agent allow-list / origin policy. Operator-controlled, on Fly.io.
- Plant data. Per-session in the browser; persisted at
  `~/.hosaka/plant.json` on the appliance.

> _the operator is the operator. the orb is the orb. you are you._
