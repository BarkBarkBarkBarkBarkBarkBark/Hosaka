# Hosaka doctor

`hosaka doctor` is the single diagnostic entrypoint for checking whether a
Hosaka runtime is healthy enough to use, update, and discover over the tailnet.

It is designed to be:

- useful for operators in a terminal
- structured enough for future MCP conversion
- profile-aware so hosted/public surfaces do not produce noisy false failures

## Why it exists

Hosaka now has multiple moving parts:

- local webserver
- touchscreen kiosk vs device mode
- Tailscale reachability
- beacon discovery
- synced frontend dependency drift
- repo vs deployed commit drift
- public/local capability gating

`hosaka doctor` turns those into one report.

## Basic usage

On the appliance:

```bash
hosaka doctor
hosaka doctor --json
hosaka doctor --strict
```

Remote read-only probe:

```bash
hosaka doctor --profile remote --host http://100.72.70.116:8421 --token "$HOSAKA_TOKEN"
```

## Current profiles

- `auto` — detect the most likely surface
- `appliance` — Pi / systemd host checks + local HTTP checks
- `desktop` — local desktop-oriented checks
- `docker-dev` — local container/dev checks
- `remote` — HTTP/API-only probe of another Hosaka node
- `hosted-public` — capability/gating checks for public deployments

## What it checks today

### Runtime

- current mode (`console` / `device`)
- webserver service state
- picoclaw gateway service state
- Chromium kiosk expectation vs actual mode
- UI bundle presence

### Network

- bind address on port `8421`
- `/api/tailscale/status`
- `/api/beacon`
- `/api/nodes`

### API posture

- `/api/health`
- `/api/v1/system/info`
- capability flag coherence

### Update drift

- repo HEAD vs running API commit
- frontend dependency drift (`node_modules`, lockfile stamp, key packages)
- local repo clean/dirty hint

### Persistence

- state directory presence/writability

## Output contract

Human output is grouped by category.

`--json` emits a stable machine-friendly structure with:

- `schema_version`
- `profile`
- `overall_status`
- `summary`
- `runtime`
- `checks[]`
- `artifacts`
- `next_actions`

That shape is intentionally close to what an MCP tool or resource would need.

## Security posture

Default doctor runs are read-only.

They do **not**:

- run `tailscale up`
- mutate mode
- perform writes
- start updates
- emit raw secrets

By default, doctor redacts suspicious secret-looking fields in output payloads.
Use `--no-redact` only when you understand the risk.

## Future MCP path

The intended later mapping is:

- CLI: `hosaka doctor`
- MCP tool: run one profile or one check family
- MCP resource: last doctor report
- MCP prompt: remediation summary derived from failed checks

So the current CLI is not throwaway work — it is the first operator surface for
that future agent-facing diagnostic layer.
