# Inbox / notifications

Hosaka now ships an append-only inbox for operator notices and lightweight
gossip across trusted nodes.

## What it is

The inbox is a small event log for things like:

- update notices
- operator reminders
- system warnings
- acknowledgements that a notice was seen

It is designed to stay **metadata-only**. It is not a transport for binaries,
packages, or executables.

## Event kinds

Current event kinds:

- `notify` — a human-readable notice
- `ack` — acknowledgement of a previous notification

## API

Under the versioned API:

- `GET /api/v1/inbox/events`
- `POST /api/v1/inbox/events`
- `POST /api/v1/inbox/events/{event_id}/ack`

These endpoints use the same auth rules as the rest of `/api/v1/*`.

## Gossip behavior

When local sync is enabled, inbox events are relayed over the same Hosaka peer
mesh used for CRDT sync, but under a separate event envelope:

```json
{
  "type": "event",
  "event": {
    "id": "...",
    "kind": "notify",
    "title": "update available",
    "body": "operator deck pulled 23f1ca0",
    "topic": "update",
    "severity": "info"
  }
}
```

Peers dedupe by stable event id and append the event to their local inbox log.

## Security posture

The inbox is intentionally limited:

- small text payloads only
- append-only log on disk
- tamper-evident hash chain
- no executable transfer
- no automatic install or execution path

If you need software delivery later, treat the inbox as a **notice plane** only:
announce that an update exists, then require a separate, verified download path.