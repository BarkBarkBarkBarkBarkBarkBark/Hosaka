---
title: OpenClaw Terminal Integration Notes
generated: 2026-04-15
openclaw_python_sdk: 2026.3.20
cmdop_sdk: 2026.4.7.2
gateway_protocol_version: 3
---

## Protocol version

Protocol version **3** (`minProtocol: 3, maxProtocol: 3`).
Source: https://docs.openclaw.ai/gateway/protocol

## Transport

WebSocket, text frames with JSON payloads.
Default URL: `ws://127.0.0.1:18789`

## Framing

- Request:  `{type: "req", id, method, params}`
- Response: `{type: "res", id, ok, payload | error}`
- Event:    `{type: "event", event, payload, seq?, stateVersion?}`

## Connect handshake

1. Server sends: `{type: "event", event: "connect.challenge", payload: {nonce, ts}}`
2. Client sends: `{type: "req", id, method: "connect", params: {…}}`
3. Server responds: `{type: "res", id, ok: true, payload: {type: "hello-ok", protocol: 3, policy: {tickIntervalMs: 15000}}}`

### Connect params (operator)

```json
{
  "minProtocol": 3,
  "maxProtocol": 3,
  "client": {"id": "hosaka-field-terminal", "version": "1.0.0", "platform": "linux", "mode": "operator"},
  "role": "operator",
  "scopes": ["operator.read", "operator.write"],
  "caps": [],
  "commands": [],
  "permissions": {},
  "auth": {"token": "…"},
  "locale": "en-US",
  "userAgent": "hosaka-field-terminal/1.0.0",
  "device": {"id": "…"}
}
```

### connect.challenge

Must be awaited in practice. The gateway sends it as the first frame.
Local loopback connections may auto-approve pairing but still receive the challenge.

## Auth precedence

1. Explicit shared `token` or `password` (`connect.params.auth.token` / `connect.params.auth.password`)
2. Explicit `deviceToken` (`connect.params.auth.deviceToken`)
3. Stored per-device token (from prior `hello-ok.auth.deviceToken`)
4. Bootstrap token (local loopback only)

Auth failures include `error.details.code` and `error.details.recommendedNextStep`.

## Chat execution methods

Official clients use `chat.send` for execution, `chat.history` for transcript, `chat.abort` to interrupt.

### chat.send params

```json
{
  "message": "user text",
  "sessionKey": "agent:main:main",
  "idempotencyKey": "unique-key"
}
```

### chat.history params

```json
{
  "sessionKey": "agent:main:main",
  "limit": 50
}
```

### chat.abort params

```json
{
  "sessionKey": "agent:main:main"
}
```

## Session methods

### sessions.resolve

```json
{"sessionKey": "agent:main:main"}
```

### sessions.create

```json
{"sessionKey": "agent:main:main", "agentId": "optional"}
```

### sessions.messages.subscribe / unsubscribe

```json
{"sessionKey": "agent:main:main"}
```

### sessions.send

```json
{"sessionKey": "agent:main:main", "message": "text", "idempotencyKey": "unique-key"}
```

## Streaming events consumed by terminal

| Event | Purpose |
|---|---|
| `chat.token` / `chat.delta` | Streamed assistant tokens |
| `chat.message` / `chat.inject` | Complete assistant messages |
| `chat.done` / `chat.end` / `chat.complete` | Run finished |
| `session.message` | Session transcript updates |
| `session.tool` | Tool execution state (running/complete) |
| `tick` | Keepalive (ignored by terminal) |
| `shutdown` | Gateway shutting down |

## Device identity

All WS clients must include `device.id` in connect params.
Local loopback connections get auto-approval for pairing.
Device state persisted at `~/.hosaka/device_state.json`.

## Notes pending gateway source inspection

The following will be validated once `openclaw` (npm) is installed and the gateway is running:

- Exact device identity signing payload format (v2/v3)
- Whether `chat.send` or `sessions.send` is the primary execution path in this version
- Exact streaming event names and payload shapes
- Whether idempotencyKey is required or optional for chat.send
- hello-ok.features.methods discovery list

## Python SDK observation

The `openclaw` Python package (2026.3.20) wraps `cmdop` SDK (2026.4.7.2).
cmdop uses **gRPC** transport (Unix socket local / TLS cloud relay).
This is a separate protocol from the OpenClaw Gateway WS on port 18789.
The terminal integration uses the WS gateway directly, not the Python/gRPC SDK.
