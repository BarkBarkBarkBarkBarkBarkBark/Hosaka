# HTTP GET / POST surface

Hosaka now ships a small, explicit outbound HTTP surface for the operator and
for agent workflows that need to hit a known external API.

This is deliberately **not** a general-purpose open proxy.

## What it is

Versioned API endpoints under `/api/v1/`:

- `POST /api/v1/http/get`
- `POST /api/v1/http/post`

These perform outbound requests from the Hosaka runtime **only if** the target
host is allowlisted.

## Why POST for both verbs?

We use POST for the control surface itself so the caller can send headers and,
for `post`, a JSON/body payload in a typed request.

## Required environment

Set at least:

- `HOSAKA_HTTP_ALLOWED_HOSTS`

Example:

```bash
export HOSAKA_HTTP_ALLOWED_HOSTS=api.github.com,api.openai.com,.example.internal
```

Optional knobs:

- `HOSAKA_HTTP_TIMEOUT` — default `15`
- `HOSAKA_HTTP_MAX_BODY` — default `65536`
- `HOSAKA_HTTP_ALLOW_PRIVATE=1` — **off by default**; only turn this on if you
  intentionally want Hosaka to reach RFC1918 / loopback targets

## Security model

Default posture is fail-closed:

- only `http` / `https`
- loopback and private IPs blocked by default
- hostname must be in `HOSAKA_HTTP_ALLOWED_HOSTS`
- writes require normal Hosaka write auth
- response body is truncated to a safe size

This is safe enough for curated API access. It is **not** safe to expose as a
wildcard fetcher.

## Request shape

### GET

```json
{
  "url": "https://api.github.com/repos/BarkBarkBarkBarkBarkBarkBark/Hosaka",
  "headers": [
    {"name": "Accept", "value": "application/json"}
  ]
}
```

### POST

```json
{
  "url": "https://api.example.com/hooks/notify",
  "headers": [
    {"name": "Content-Type", "value": "application/json"}
  ],
  "json_body": {
    "event": "hosaka.update.available",
    "node": "operator-deck"
  }
}
```

## Response shape

```json
{
  "url": "https://api.github.com/repos/...",
  "status": 200,
  "content_type": "application/json; charset=utf-8",
  "headers": {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "public, max-age=60"
  },
  "body": "{...}",
  "truncated": false
}
```

## Suggested uses

- hit GitHub release metadata
- hit a billing/subscription webhook endpoint you own
- hit a managed Fly control-plane API
- hit an internal service you have explicitly allowlisted

## Strong warning

Do **not** set:

```bash
HOSAKA_HTTP_ALLOWED_HOSTS=*
```

That would turn this into a dangerous SSRF-style pivot. Keep the host list
small and specific.