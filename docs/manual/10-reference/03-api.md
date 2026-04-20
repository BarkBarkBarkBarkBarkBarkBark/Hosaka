# 10.03 · the API

The appliance exposes a small REST API at `http://<host>:8421/api/v1/*`.
This is the surface `hosakactl` uses, and the surface the `/device`
page uses, and the surface _you_ can use from a script.

OpenAPI spec lives at:

```
http://<host>:8421/openapi.json
```

…and rendered (when docs are built):

```
https://<your-gh-user>.github.io/Hosaka/api.html
```

---

## auth model

| Source of request | Reads | Writes (POST/DELETE/PUT) |
|---|---|---|
| `127.0.0.1` (loopback) | ✓ always | ✓ always |
| LAN with `Authorization: Bearer <token>` | ✓ | ✓ |
| LAN without token | ✓ | ✗ 403 |

Token at `/etc/hosaka/api-token`. See [accounts](../04-accounts.md) and
[hosakactl install](../07-the-laptop-client/01-install-and-link.md#step-3--get-the-bearer-token).

---

## the endpoints

### `GET /api/v1/health`

Cheap liveness check. Returns whether the webserver is up and which
keys are configured.

```bash
curl -fsS http://hosaka.local:8421/api/v1/health | jq .
```

```json
{
  "ok": true,
  "checks": {
    "webserver": "up",
    "picoclaw_gateway": "up",
    "openai_key": false,
    "gemini_key": true
  }
}
```

### `GET /api/v1/system/info`

Full snapshot. The data the `/device` page renders.

```bash
curl -fsS http://hosaka.local:8421/api/v1/system/info | jq .
```

Returns hostname, uptime, ip, ssid, ram, cpu, mode, services, urls.

### `GET /api/v1/mode`

Current mode + whether it's persisted.

```json
{ "mode": "console", "persist": true }
```

### `POST /api/v1/mode`

Switch mode. **Requires token from LAN.**

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "device", "persist": true}' \
  http://hosaka.local:8421/api/v1/mode
```

`mode`: `console` or `device`.

### `GET /api/v1/wifi`

List saved + visible networks.

### `POST /api/v1/wifi`

Add a network. **Requires token from LAN.**

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ssid": "Cafe Free WiFi", "password": "secret"}' \
  http://hosaka.local:8421/api/v1/wifi
```

### `DELETE /api/v1/wifi/<ssid>`

Forget a saved network. **Requires token.**

### `GET /api/v1/services`

List the systemd units Hosaka knows about + their state.

### `POST /api/v1/services/<unit>/restart`

Restart a whitelisted unit. **Requires token.**

Whitelist:

- `hosaka-webserver.service`
- `picoclaw-gateway.service`
- `hosaka-mode.service`
- `hosaka-device-dashboard.service`

---

## error shapes

Errors come back as JSON with a `detail` field, in keeping with FastAPI
defaults:

```json
{
  "detail": "missing or invalid bearer token"
}
```

HTTP codes used:

- `200` — fine
- `401` — token missing
- `403` — token present but invalid, or write attempted from LAN
  without token
- `404` — unknown endpoint or unknown unit/ssid
- `409` — conflict (e.g. trying to add a wifi that's already saved)
- `500` — something the orb chose not to talk about

---

## the hosted-side endpoints

Two non-`/api/v1/*` endpoints exist on the hosted edition:

### `POST /api/gemini` (Vercel Edge)

Brokers the `/ask` command. Keeps `GEMINI_API_KEY` server-side.

```bash
curl -fsS https://terminal.hosaka.xyz/api/gemini \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"signal check"}]}' | jq .
```

### `WS /ws/agent` (Fly.io agent server)

The picoclaw bridge. Gated by `HOSAKA_ACCESS_TOKEN` (which must equal
the SPA's `VITE_HOSAKA_MAGIC_WORD`).

```
wss://agent.hosaka.app/ws/agent?token=<word>
```

The hosted SPA opens this when you say the magic word or run
`/agent on`.

---

## scripting the API

### one-liner status

```bash
curl -fsS -H "Authorization: Bearer $(cat ~/.hosaka_token)" \
  http://hosaka.local:8421/api/v1/system/info | jq -r .ssid
```

### switch mode and wait

```bash
TOKEN=$(cat ~/.hosaka_token)
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode":"device","persist":true}' \
  http://hosaka.local:8421/api/v1/mode

until curl -fsS http://hosaka.local:8421/api/v1/mode | jq -e '.mode == "device"'; do
  sleep 1
done
echo "now in device mode."
```

### the smoke test

The cleanest scripted check is just to call `hosakactl test`. Or, for
the full battery (auth boundaries + legacy helpers):

```bash
bash ~/Cursor_Folder/Cursor_Codespace/local_workspace/scripts/hosaka_smoke.sh
```

Both exit 0 on green, 1 on any failure.
