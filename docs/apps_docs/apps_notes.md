# Hosaka Apps — notes

Status snapshot for the manifest-backed app subsystem. The runtime is the
source of truth; this file follows it.

## what ships today

- Registry: [hosaka-apps/registry.yaml](../../hosaka-apps/registry.yaml)
- Schema (maintainer reference): [hosaka-apps/manifest.schema.yaml](../../hosaka-apps/manifest.schema.yaml)
- Manifests: [spotify.yaml](../../hosaka-apps/apps/spotify.yaml),
  [foliate.yaml](../../hosaka-apps/apps/foliate.yaml),
  [discord.yaml](../../hosaka-apps/apps/discord.yaml),
  [kcc.yaml](../../hosaka-apps/apps/kcc.yaml)
- Frontend loader: [frontend/src/apps/hosakaApps.ts](../../frontend/src/apps/hosakaApps.ts)
  with build-time `import.meta.glob` seed plus a runtime
  `refreshHosakaApps()` override fed by the host.
- Frontend host bridge: [frontend/src/apps/flatpakBackend.ts](../../frontend/src/apps/flatpakBackend.ts) — wraps
  Electron IPC and falls back to the HTTP API.
- Electron host: [kiosk/main.js](../../kiosk/main.js) and
  [kiosk/preload.js](../../kiosk/preload.js).
- HTTP fallback: [hosaka/web/api_v1.py](../../hosaka/web/api_v1.py) under
  `/api/v1/apps/*` (mock by default, real shell-out behind `HOSAKA_APPS_HTTP=real`).
- Panels: [AppStorePanel.tsx](../../frontend/src/panels/AppStorePanel.tsx) (Flathub
  catalog + stage), [MusicPanel.tsx](../../frontend/src/panels/MusicPanel.tsx) (radio + library populator).
- Shell commands: `/apps`, `/app <id>`, `/install <id>`, `/launch <id>`,
  `/search <query>`, `/store`, `/listen`, `/library populate <genre>`.

## host capabilities

The frontend asks the host for capabilities via `apps:capabilities` and
treats the response as authoritative.

| host        | platform        | flatpak | mocked | notes                              |
| ----------- | --------------- | ------- | ------ | ---------------------------------- |
| electron    | linux           | real    | no     | `flatpak --version` probed at boot |
| electron    | darwin / win32  | n/a     | yes    | `HOSAKA_FAKE_FLATPAK` auto-on      |
| web (HTTP)  | any             | mock    | yes    | unless `HOSAKA_APPS_HTTP=real`     |

`HOSAKA_FAKE_FLATPAK=1` forces mock mode anywhere; `=0` forces real even on
darwin/win32 (will fail loudly).

## IPC surface (Electron host)

Exposed by [kiosk/preload.js](../../kiosk/preload.js) on `window.hosakaAppHost`:

| method                  | purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `listManifests()`       | runtime list of installed manifests                  |
| `capabilities()`        | host/platform/flatpak/mocked snapshot                |
| `flatpakAvailable()`    | `flatpak --version` probe                            |
| `flathubConfigured()`   | remote presence check + bootstrap                    |
| `flatpakInstalled(id)`  | `flatpak list --app` lookup                          |
| `installApp(id)`        | manifest-driven argv, 5-min timeout, SIGTERM on T/O  |
| `launchApp(id)`         | manifest-driven argv, detached                       |
| `flathubSearch(q)`      | proxies Flathub `/api/v2/search/<q>` via `net`        |
| `flathubMeta(appId)`    | proxies Flathub `/api/v2/appstream/<id>` via `net`    |
| `stageManifest(payload)`| writes a new YAML to `hosaka-apps/apps/<id>.yaml`     |

## HTTP surface (web fallback)

All under `/api/v1/apps`:

| method | path                       | auth          | mockable |
| ------ | -------------------------- | ------------- | -------- |
| GET    | `/`                        | none          | yes      |
| GET    | `/capabilities`            | none          | yes      |
| GET    | `/{id}/status`             | none          | yes      |
| POST   | `/{id}/install`            | require_write | yes      |
| POST   | `/{id}/launch`             | require_write | yes      |
| POST   | `/stage`                   | require_write | yes      |

`require_write` accepts loopback callers without a token; LAN callers need
`Authorization: Bearer $HOSAKA_API_TOKEN`.

## safety choices

- argv arrays only; kiosk uses `spawn(..., { shell: false })`.
- Install and launch are separate operations; nothing auto-launches.
- `--noninteractive` is in new manifests so flatpak never blocks on tty.
- 5-minute install timeout, SIGTERM on overrun.
- Hosaka never stores third-party credentials.
- Stage endpoint validates the slug, normalizes the id, and writes only
  inside `hosaka-apps/apps/`.

## known compromises

- Schema validation is documentation-first. We do not reject unknown fields.
- Flathub fetches use the public JSON API (`api/v2`) without caching.
- `populateLibrary()` for music keeps tracks in localStorage only.
- Browser-only sessions get the mocked HTTP backend; real installs require
  the kiosk on a Linux host (or `HOSAKA_APPS_HTTP=real`).

## next likely additions

- Capability badges in the app inspector (host, mock, flatpak).
- Cache Flathub responses for the session.
- Surface install/launch logs in the shell.
- Dependency hints via `flatpak remote-info` before install.
- Per-host registry overlays (e.g. hide heavy apps on the picoclaw).
