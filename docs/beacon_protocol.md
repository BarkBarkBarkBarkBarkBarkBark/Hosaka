# Hosaka beacon protocol

Hosaka now ships a small **beacon** for node discovery and capability gossip on
the tailnet. This is intentionally separate from the CRDT documents used for
`todo`, `messages`, and other synced state.

## Why this exists

Before the beacon, node discovery was mostly heuristic:

- enumerate Tailscale peers
- probe each peer's `/api/health`
- treat `{"web":"ok"}` as "probably a Hosaka"

That worked for the first Nodes panel, but it did not tell us what a node could
actually do. The beacon adds a small capability manifest so Hosaka can answer:

- which build / commit is this peer running?
- is it public or operator-owned?
- does it expose sync, Tailscale, settings, or the web panel?
- when was this peer last seen?

## Current scope

**The beacon is metadata only.** It does not replace the CRDT sync path and it
does not carry todos or chat payloads.

Current uses:

1. local capability advertisement in `/api/health`
2. peer gossip in `/ws/sync` hello frames
3. durable peer cache for the Nodes panel

Future uses:

- routing updates/notices to the right nodes
- capability-based handoff (`message inbox`, `software update`, `broker sync`)
- Fly.io rendezvous registration

## Wire shape

Protocol version: `1`

Example beacon:

```json
{
  "protocol": 1,
  "node_id": "c7c0a49c-74d3-5198-b0bb-7d2d0d4c8576",
  "hostname": "hosaka-pi",
  "dns_name": "hosaka-pi.tailnet.ts.net",
  "ip": "100.88.4.21",
  "os": "linux",
  "commit": "23f1ca0",
  "version": "23f1ca0",
  "transport": ["health", "sync.ws"],
  "capabilities": [
    "api.v1",
    "beacon.v1",
    "sync.ws",
    "tailscale.cli",
    "nodes.panel",
    "web.panel",
    "settings.drawer"
  ],
  "public_mode": false,
  "tailscale_connected": true,
  "last_seen": 1777111111.12,
  "source": "local"
}
```

## Where it appears

### `/api/health`

Local appliance builds include a `beacon` object in the health payload so peers
can learn capability metadata during normal reachability probes.

### `/api/beacon`

Returns:

- `self`: the local beacon
- `peers`: last seen remote beacons cached on disk

This is intended as a debug/inspection endpoint for the Nodes panel and future
operator tooling.

### `/ws/sync`

When a Hosaka peer dials another Hosaka peer over the sync websocket, its first
`hello` frame now includes the local beacon. That lets peers gossip capability
changes faster than the periodic `/api/nodes` probe loop.

## Persistence

Remote peer beacons are cached in:

- `~/.hosaka/state/beacons.json`

This cache is TTL-based and intentionally disposable. It is not a source of
truth; it is just a warm-start memory so node metadata survives process restarts.

## Design notes

- Public mode is a hard boundary. Public deployments advertise `public_mode: true`
  and do not mount the local-only Tailscale or sync routes.
- Capabilities are additive. Old peers can ignore unknown capability strings.
- The beacon is not an auth layer. Tailnet ACLs and API auth still matter.
- The beacon is the right place for **presence/capabilities**, not for mutable
  collaborative documents.

## Planned next steps

1. separate `messages` chat from an append-only update/event stream
2. introduce capability-targeted routing for update notices and inbox delivery
3. add a Fly.io broker that consumes the same beacon shape for rendezvous