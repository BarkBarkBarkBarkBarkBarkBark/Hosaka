# Flathub plan — idyllic version

A sketch of where the Hosaka ↔ Flathub bridge wants to grow. The
short-term implementation lives in
[apps_notes.md](./apps_notes.md). This file is the north star.

## guiding principles

1. **Hosaka Apps, not Flatpak.** Flathub is a backend detail. The user
   sees "Install Discord", never `flatpak install -y flathub …`.
2. **Manifest is law.** The kiosk never executes free-form commands. Every
   install or launch resolves through a manifest in `hosaka-apps/apps/`.
3. **Mock-first.** Every code path works on macOS dev with no flatpak
   installed. Real installs only happen on a Linux host that opted in.
4. **No silent network spend.** Flathub fetches go through a small,
   cacheable surface; we never scrape, we use `/api/v2/*` JSON.
5. **No third-party credentials.** Login happens inside each app, in its
   own sandbox. Hosaka never persists user creds for any guest app.

## the lifecycle

```
discover  →  preview  →  stage  →  install  →  launch  →  inspect
   │           │          │          │           │           │
 search      meta      write yaml  flatpak    flatpak     status +
 (api/v2)   (api/v2)   manifest   install     run         logs
```

### 1. discover

- UI: `AppStorePanel` (search box + curated chips: editors, music,
  reading, comms, dev tools, retro).
- Source: `https://flathub.org/api/v2/search/<q>` via the kiosk `net`
  module (no CORS pain) or directly from the browser when in HTTP mode.
- Output: list of `{app_id, name, summary, icon, verified}`.

### 2. preview

- UI: app card with screenshots, license, project URL, runtime size.
- Source: `https://flathub.org/api/v2/appstream/<app_id>`.
- Decisions surfaced before install: download size, runtime
  dependencies, account requirement (heuristic from project URL).

### 3. stage

- The user clicks **Add to Hosaka**.
- Frontend builds a minimal manifest (id, name, category guess,
  flatpak_id, install/launch argv) and POSTs to `apps:stage-manifest`
  (kiosk) or `/api/v1/apps/stage` (HTTP).
- Host writes `hosaka-apps/apps/<id>.yaml` with `--noninteractive` baked
  into the install argv.
- The registry refreshes; the new app shows up under `/apps`.

### 4. install

- `apps:install <id>` resolves the manifest argv and spawns flatpak
  with `shell:false`, a 5-minute timeout, and SIGTERM on overrun.
- Mock mode echoes back `{ ok:true, installed:true, host:"mock" }` and
  flips the in-memory installed set.
- Real mode streams stdout/stderr lines back to the shell.

### 5. launch

- `apps:launch <id>` checks `flatpak list --app` then spawns the launch
  argv detached.
- Mock mode pretends it launched.
- Failures surface as actionable shell output (e.g. "flathub remote
  missing — run /admin flathub bootstrap").

### 6. inspect

- `/app <id>` prints the resolved manifest, capability badges, install
  status, last launch result.
- The app inspector panel shows the same data with a "Remove" button
  that deletes the manifest only (it does not uninstall flatpak — that
  stays explicit).

## the manifest contract

Every staged or hand-authored manifest must satisfy
[manifest.schema.yaml](../../hosaka-apps/manifest.schema.yaml). Notable
invariants:

- `flatpak_id` matches the appstream id from Flathub.
- `install.command[0] == "flatpak"` and `launch.command[0] == "flatpak"`.
- `--noninteractive` lives in `install.command` for any new manifest.
- `hosaka_manages_credentials` is always `false`.
- `aliases` includes the bare slug.

Future: a real validator (pydantic on the backend, zod on the frontend)
that rejects manifests that fail these invariants.

## host matrix

| host                  | platform | install backend  | notes                          |
| --------------------- | -------- | ---------------- | ------------------------------ |
| Electron kiosk        | Linux    | real flatpak     | the canonical target           |
| Electron kiosk        | macOS    | mock             | `HOSAKA_FAKE_FLATPAK` auto-on  |
| Electron kiosk        | Windows  | mock             | dev only                       |
| Browser → HTTP API    | any      | mock or real     | server controls the toggle     |
| picoclaw bridge       | Linux    | real flatpak (+ throttle) | future: per-host policy |

## what we are deliberately not doing

- No `flatpak install` of arbitrary ids from the shell.
- No piping shell strings into spawn.
- No DRM-bypassing capture of audio/video from guest apps.
- No credential vault for third-party apps.
- No background auto-update of installed apps without user action.

## roadmap, in order of cheapness

1. **Capability badges** in `AppStorePanel` (host, mock, flatpak version).
2. **Session cache** for Flathub search/meta calls.
3. **Live install logs** streamed to the shell via `apps:install-log`.
4. **`flatpak remote-info` preview** before install (size, runtime).
5. **Batch install** with sequential argv and a single progress view.
6. **Per-host overlays** in `registry.yaml` (`only_on: [linux]`,
   `not_on: [picoclaw]`).
7. **Real schema validator** shared between kiosk and backend.
8. **Optional Flathub auth** for verified-developer ribbons (read-only).
9. **App removal** that calls `flatpak uninstall` behind an explicit
   confirm, separate from manifest removal.
10. **Curated collections** (`/store --collection retro`) backed by a
    small static list checked into the registry.

## acceptance, in plain words

- A first-time user on the kiosk can type `/store`, search for VLC,
  click install, watch a progress line, and then type `/launch vlc`.
- A developer on macOS can do the exact same flow and see mock results
  with no errors and no flatpak installed.
- A LAN client can hit `/api/v1/apps/*` with a bearer token and get the
  same shape of responses, mocked unless the server opts into real.
- The shell never executes a command that did not come from a manifest.
- Removing a Hosaka App is a one-step, reversible action that does not
  silently uninstall the underlying flatpak.
