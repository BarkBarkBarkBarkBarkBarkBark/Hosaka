# Local bridge + gateway implementation guide

This document is the implementation runbook for the next Hosaka phase:

1. a **local bridge** that lets a public Hosaka site detect and hand off to a
   local Hosaka node safely
2. a **managed Fly control plane** that can broker presence, pairing, and
   optional managed terminal sessions
3. a **Docker initialization check** so you can verify the local Hosaka runtime
   is actually ready before layering on bridge features

This file lives in the **Hosaka repo** because the raw runtime belongs here.
The **public web controls** remain in the field-terminal repo.

---

## Repo ownership split

Keep this boundary hard:

### Hosaka repo owns

- the local FastAPI runtime
- Tailscale and peer discovery
- beacon + inbox gossip
- the local bridge listener on loopback
- the operator approval path for remote actions
- Docker runtime checks

### field-terminal repo owns

- terminal.hosaka.xyz UI
- public-mode controls and fail-closed feature flags
- managed Fly backend / hosted gateway configuration
- Vercel deployment settings
- subscription/control-plane UX

If a feature can execute shell commands, touch the local filesystem, or pivot
onto another node, it belongs in **Hosaka**, not in the hosted wrapper.

---

## Goal state

The long-term safe flow should look like this:

```text
terminal.hosaka.xyz
        │
        │ https
        ▼
  hosted field-terminal UI
        │
        │ loopback handshake only
        ▼
  local Hosaka bridge (127.0.0.1 only)
        │
        │ authenticated local control
        ▼
  local Hosaka runtime
        │
        ├── Tailscale peers
        └── optional Fly broker
```

The browser is a **presentation layer**. The local Hosaka runtime remains the
trusted control point.

---

## Required keys and secrets

Below is the operator checklist. It separates **required now** from
**required when you add the bridge/control plane**.

## Required now — local Hosaka / Docker runtime

### 1. LLM provider key

You need **one** of:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

Use whichever provider you want to wire into picoclaw or the hosted backend.

### 2. Hosaka API token

For remote `/api/v1/*` writes, you need:

- `/etc/hosaka/api-token` on appliance installs, or
- `HOSAKA_API_TOKEN` if you are injecting a token via environment

This is what protects write routes such as inbox post / ack and mode changes.

### 3. Optional Tailscale login / auth

You need either:

- an interactive Tailscale login, or
- a Tailscale auth key if you later automate unattended joins

Hosaka can already work without Tailscale, but the bridge/gossip model depends
on private node discovery.

## Required for the hosted Fly gateway

### 4. Fly secret for hosted agent access

- `HOSAKA_ACCESS_TOKEN`

This is the passphrase gate for the hosted Fly agent/backend.

### 5. Hosted origin allowlist

- `HOSAKA_ALLOWED_ORIGINS`

Set this to the exact public domains that should be allowed to talk to the
hosted backend.

### 6. Fly provider key

Again, one of:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

for the hosted Fly backend.

## Required when you add the local bridge

These are **new keys to add when you implement the bridge**. They are not all
wired into the current codebase yet, so treat them as part of the bridge work.

- `HOSAKA_BRIDGE_PAIRING_SECRET`
  - used to mint or verify short-lived pairing tokens between the public site
    and the local loopback bridge
- `HOSAKA_BRIDGE_ALLOWED_ORIGINS`
  - exact origin allowlist, for example `https://terminal.hosaka.xyz`
- `HOSAKA_BRIDGE_BIND`
  - recommended default: `127.0.0.1:8422`

Do **not** expose the bridge on `0.0.0.0`.

---

## Human setup steps

## A. Bring up the local Hosaka Docker runtime

From the Hosaka repo root:

```bash
cd /path/to/Hosaka
cp .env.example .env   # if you make one later; for now create .env manually if needed
./docker/dev.sh up
```

If you need the interactive terminal instead:

```bash
./docker/dev.sh tui
```

Recommended `.env` values for local dev:

```bash
OPENAI_API_KEY=sk-...
# or
GEMINI_API_KEY=AIza...

HOSAKA_PUBLIC_MODE=0
HOSAKA_SYNC_ENABLED=1
HOSAKA_TAILSCALE_API_ENABLED=1
HOSAKA_INBOX_ENABLED=1
```

If `./docker/dev.sh up` fails with `bind: address already in use` on `8421`,
you already have another Hosaka (or another local service) bound there.
Common fix:

```bash
hosaka down  # if you launched the installer-managed local runtime
# or stop the conflicting process, then rerun ./docker/dev.sh up
```

## B. Verify the local runtime is initialized

Run:

```bash
bash scripts/check_docker_init.sh
```

That check is expected to confirm:

- Docker compose service is running
- `/progress` responds
- `/api/health` responds
- `/api/v1/health` responds from loopback inside the container
- `picoclaw` exists in the container
- `tailscale` exists in the container
- the built UI exists in `hosaka/web/ui/`
- inbox and beacon APIs respond

If any of these fail, fix the runtime first. Do **not** build the bridge on a
half-initialized container.

## C. Bring up the hosted field-terminal stack

Use the field-terminal repo for the public site and managed backend pieces.

Hosted/public controls must stay fail-closed there.

## D. Add the local bridge

Recommended first bridge surface:

- `GET /bridge/status`
- `POST /bridge/open-local`
- `POST /bridge/pair`

Nothing more at first.

The bridge should expose only:

- app present / version / node id
- whether local Hosaka is ready
- the local UI URL for handoff
- a short-lived pairing state

The bridge should **not** expose:

- arbitrary fetch/proxy
- shell execution
- file read/write
- unrestricted peer scanning
- SSH

## E. Add the Fly control plane

Implement this in stages:

1. shared control plane
2. pairing
3. presence registry
4. mailbox / inbox relay
5. premium dedicated worker

Start with **shared broker first**. Do not start with “every user gets a Fly
machine” on day one.

---

## Docker initialization checklist

Before you trust a Docker deployment, verify these from the host:

```bash
docker compose -f docker/compose.yml -p hosaka ps
curl -sf http://127.0.0.1:8421/progress | python3 -m json.tool
curl -sf http://127.0.0.1:8421/api/health | python3 -m json.tool
```

Then verify inside the running container:

```bash
docker compose -f docker/compose.yml -p hosaka exec hosaka bash -lc '
  command -v picoclaw &&
  command -v tailscale &&
  test -d /opt/hosaka-field-terminal/hosaka/web/ui &&
  /opt/hosaka-field-terminal/.venv/bin/python - <<"PY"
import urllib.request
for url in (
    "http://127.0.0.1:8421/api/health",
    "http://127.0.0.1:8421/api/v1/health",
    "http://127.0.0.1:8421/api/beacon",
    "http://127.0.0.1:8421/api/v1/inbox/events",
):
    with urllib.request.urlopen(url, timeout=5) as r:
        print(url, r.status)
PY'
```

Expected result: all return `200`.

If `api/v1/health` fails from inside the container, the loopback auth path or
server startup is not healthy yet.

---

## Security constraints for the bridge

These are non-negotiable if you want the feature without turning the site into
a giant security hole.

1. bind the bridge to `127.0.0.1` only
2. strict origin allowlist
3. require explicit user gesture before any action
4. no direct browser-to-SSH
5. no raw proxy/fetch endpoint
6. no file transfer or executable sync through inbox/gossip
7. keep the hosted site as discovery + handoff, not a privileged executor

If you break any of those, you are building a local network pivot for the open
internet.

---

## Worst-case outcomes to design against

### Malicious website probes localhost

Defense:

- loopback bridge with strict CORS/origin checks
- tiny read-only surface
- pairing tokens

### Hosted site becomes an SSH launcher

Defense:

- SSH only from local Hosaka backend
- explicit operator approval
- allowlisted machines / Tailscale tags

### Malicious tailnet node gossips dangerous data

Defense:

- signed beacons / signed inbox events next
- no binaries in gossip
- no automatic install path from inbox events

### Fly bill spikes

Defense:

- shared broker first
- premium dedicated workers later
- quotas, rate limits, and idle shutdown

---

## Recommended implementation order

1. local bridge status + handoff only
2. pairing token flow
3. read-only remote node status via local Hosaka
4. Fly presence registry
5. shared mailbox / inbox fanout
6. premium managed Fly workers

That order keeps the risk bounded while still moving toward the subscription
model.
