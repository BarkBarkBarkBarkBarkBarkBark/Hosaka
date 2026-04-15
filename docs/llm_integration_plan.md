# Hosaka LLM Integration Plan

> `chat` and `code` commands — bringing conversational AI and raw shell access
> to the Hosaka console.

---

## Overview

Two new console commands extend Hosaka from an appliance shell into an
operator workstation:

| Command | Mode | What it does |
|---|---|---|
| `code` | Sub-shell | Drops to `$SHELL` (or `/bin/bash`). `exit` / Ctrl-D returns to Hosaka. |
| `chat` | LLM REPL | Every line goes to an LLM. Responses stream to stdout. `/back` or Ctrl-C returns. |
| `chat <prompt>` | One-shot | Single query, print response, stay in `hosaka>` prompt. |

---

## Architecture

```
┌──────────────────────────────────┐
│         hosaka console           │
│  ┌────────┐    ┌──────────────┐  │
│  │  code   │    │    chat      │  │
│  │ (shell) │    │  (LLM REPL) │  │
│  └────────┘    └──────┬───────┘  │
│                       │          │
│              ┌────────▼────────┐ │
│              │  LLM Router     │ │
│              │                 │ │
│              │  1. OpenClaw    │ │
│              │  2. OpenAI API  │ │
│              └─────────────────┘ │
└──────────────────────────────────┘
```

---

## `code` command — raw terminal

### Behavior

1. User types `code` at the `hosaka>` prompt.
2. Hosaka prints `"Entering shell. Type 'exit' or Ctrl-D to return."`.
3. Spawns `os.environ.get("SHELL", "/bin/bash")` via `subprocess.run()`
   with `stdin/stdout/stderr` inherited (no capture).
4. When the sub-shell exits, Hosaka prints `"Back in Hosaka console."` and
   resumes the REPL.

### Implementation sketch

```python
import os
import subprocess

def _enter_code_mode(current_dir: Path) -> None:
    shell = os.environ.get("SHELL", "/bin/bash")
    print(f"Entering shell ({shell}). Type 'exit' or Ctrl-D to return.")
    subprocess.run([shell], cwd=str(current_dir))
    print("Back in Hosaka console.")
```

No dependencies. Works offline. Zero config.

---

## `chat` command — LLM conversation

### Behavior

1. User types `chat` → enters conversational REPL.
   User types `chat how do I mount a USB drive?` → one-shot, stays in console.
2. In REPL mode, every line of input is sent to the LLM.
3. Responses are streamed token-by-token to stdout.
4. `/back`, `/exit`, or Ctrl-C exits chat mode and returns to `hosaka>`.

### Prompt framing

Every conversation starts with a system prompt:

```
You are Hosaka, a field terminal assistant on a cyberdeck running Debian Linux.
Be concise. Prefer shell commands and practical answers.
The operator's working directory is {current_dir}.
The device hostname is {state.hostname}.
```

Conversation history is held in memory for the session (cleared on `/back`).

---

## LLM Router — OpenClaw first, OpenAI fallback

### Priority chain

```
1. OpenClaw (local or LAN)  →  preferred, already in onboarding
2. OpenAI API               →  fallback, requires OPENAI_API_KEY
3. Offline stub             →  if both unavailable, use offline/assist.py
```

### OpenClaw path (preferred)

OpenClaw is already configured during onboarding (`openclaw_path`,
`openclaw_enabled`, `openclaw_ready` in state).

**Option A — HTTP API (recommended)**

If OpenClaw exposes a local HTTP endpoint (e.g. `http://localhost:11434/v1/chat/completions`
or a compatible API), Hosaka sends requests directly:

```python
import httpx

OPENCLAW_ENDPOINT = f"http://localhost:11434/v1/chat/completions"

async def chat_openclaw(messages: list[dict], stream: bool = True):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            OPENCLAW_ENDPOINT,
            json={"messages": messages, "stream": stream},
            timeout=120,
        )
        if stream:
            async for chunk in resp.aiter_lines():
                yield chunk
        else:
            yield resp.json()["choices"][0]["message"]["content"]
```

The endpoint URL is derived from `openclaw_path` + state, or set explicitly
via a new env var `OPENCLAW_API_URL`.

**Option B — subprocess / CLI**

If OpenClaw only exposes a CLI:

```python
def chat_openclaw_cli(prompt: str, openclaw_bin: str) -> str:
    result = subprocess.run(
        [openclaw_bin, "ask", prompt],
        capture_output=True, text=True, timeout=120,
    )
    return result.stdout
```

Less ideal (no streaming), but works as a bridge.

### OpenAI API path (fallback)

When OpenClaw is unavailable (`openclaw_ready=false` or health check fails),
fall back to the OpenAI API if `OPENAI_API_KEY` is set.

```python
import httpx

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

async def chat_openai(messages: list[dict], model: str = "gpt-4o-mini"):
    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            OPENAI_URL,
            headers=headers,
            json={"model": model, "messages": messages, "stream": True},
            timeout=120,
        )
        async for chunk in resp.aiter_lines():
            yield chunk
```

### Offline stub (last resort)

If no LLM backend is reachable, route to the existing `offline/assist.py`
intent classifier for keyword-based guidance, and print:

```
LLM unavailable. Showing offline guidance.
Connect OpenClaw or set OPENAI_API_KEY for full chat.
```

---

## New env vars

| Variable | Default | Description |
|---|---|---|
| `OPENCLAW_API_URL` | `http://localhost:11434/v1/chat/completions` | OpenClaw API endpoint |
| `OPENAI_API_KEY` | *(unset)* | OpenAI API key for fallback |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model to use with OpenAI fallback |
| `HOSAKA_CHAT_TIMEOUT` | `120` | Max seconds to wait for LLM response |

---

## New dependency

Add `httpx` to `requirements-hosaka.txt` for async HTTP:

```
httpx>=0.27,<1.0
```

No OpenAI SDK needed — raw HTTP keeps the dependency tree small and works
identically for OpenClaw and OpenAI (both speak the OpenAI chat completions
wire format).

---

## File plan

| File | Purpose |
|---|---|
| `hosaka/llm/__init__.py` | Package init |
| `hosaka/llm/router.py` | LLM routing: OpenClaw → OpenAI → offline |
| `hosaka/llm/openclaw.py` | OpenClaw HTTP + CLI adapters |
| `hosaka/llm/openai.py` | OpenAI API adapter |
| `hosaka/llm/chat.py` | `chat` REPL loop + one-shot handler |
| `hosaka/main_console.py` | Wire up `code` and `chat` commands |
| `tests/test_hosaka_chat.py` | Unit tests for router + adapters |

---

## Integration into main_console.py

```python
# In run_main_console(), add before the shell passthrough:

elif raw == "code":
    _enter_code_mode(current_dir)
elif raw == "chat":
    _enter_chat_mode(current_dir, state)
elif raw.startswith("chat "):
    _one_shot_chat(raw[5:], current_dir, state)
```

---

## Phased delivery

### Phase 1 — `code` command (no dependencies)
- Add `_enter_code_mode()` to `main_console.py`
- Add `code` to `DEFAULT_HELP_TOPICS`
- Ship immediately

### Phase 2 — `chat` with OpenClaw
- Create `hosaka/llm/` package
- Implement OpenClaw HTTP adapter
- Implement chat REPL loop
- Add `httpx` to requirements
- Wire into `main_console.py`
- Test with OpenClaw running locally

### Phase 3 — OpenAI fallback
- Add OpenAI adapter (same wire format, different URL + auth header)
- Add router logic (try OpenClaw → try OpenAI → offline stub)
- Add env var documentation

### Phase 4 — Conversation context
- Session-scoped message history
- System prompt with device context (hostname, IP, working dir)
- `/clear` to reset conversation in chat mode
- `/model` to switch models if multiple available

---

## Security notes

- `OPENAI_API_KEY` should be in `.env` or systemd credentials, never in state.json.
- OpenClaw runs locally — no API key needed for local inference.
- Chat history is in-memory only, never persisted to disk.
- The `code` sub-shell inherits the Hosaka process's permissions — on an
  appliance this is typically root via the systemd unit.
