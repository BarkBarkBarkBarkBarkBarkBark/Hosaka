# Hosaka app framework progress

Hosaka already prefers Electron on-device, but gracefully falls back to the browser/web experience elsewhere.

This note is for maintainers and agents. It explains what shipped, what is only modeled, and what remains to build.

## What shipped in this pass

### 1. Local repo dev without Docker

A new local command now exists in [scripts/hosaka](../scripts/hosaka):

- `./scripts/hosaka dev` — starts the Vite app on `http://localhost:5173` and opens the browser
- `./scripts/hosaka dev --electron` — starts Vite and the Electron kiosk host together

This is meant for repo-local development, so you can iterate on the UI without:

- pushing to GitHub
- waiting for hosted build actions
- pulling back into a container
- remembering Docker syntax for basic frontend work

### 2. Electron-first app registry metadata

[frontend/src/ui/appRegistry.ts](../frontend/src/ui/appRegistry.ts) is now the source of truth for:

- launcher-visible built-ins
- planned integrations
- primary host choice
- fallback hosts
- install method
- host scope
- embed policy
- maintainer notes
- agent notes

Registry now also documents host requirements and install policy.

### 3. Planned integrations were added to the registry

The registry now explicitly models these planned integrations:

- `hosaka radio` via `music`
- `spotify`
- `kindle`
- `discord`
- `app_store`
- `simulcast`

This does **not** mean they launch yet. It means the app directory, maintainers, and agents can reason about them before implementation lands.

### 4. App directory metadata is visible

[frontend/src/panels/DesktopPanel.tsx](../frontend/src/panels/DesktopPanel.tsx) now shows app-directory metadata badges and notes for:

- family (`core` or `integration`)
- status
- primary host
- install method
- owner note
- AI note

Planned apps appear here before shipping so maintainers and agents can reason about them.

## Current alignment

- Hosaka already ships an Electron kiosk host wrapping the SPA in one fullscreen native window.
- The same frontend bundle still runs in plain browsers through a built-in browser fallback.
- Its Web panel already supports native webview rendering for inline sites inside Electron.
- App registry and window state already model launchable surfaces, open windows, and active focus.

## Install policy

- Prefer Electron desktop apps, allow Linux/Windows package installs when necessary, and disable features on web when unsupported.
- Linux app stores are acceptable, but Electron remains preferred.
- Windows nodes may use package managers, but Electron remains the preferred option.
- External apps should be launched via capability-checked handoff, not assumed embedded.

## External apps

There isn’t a true external app store yet.

The `electron-app-store` repo can inspire catalog UX, but it should not become a dependency today.

The `electron-app-store` repo is stale and should remain reference-only.

Current plan:

- keep Hosaka dependency-light
- keep catalog/install policy in the registry first
- add real host handoff later through the Electron shell
- keep browser fallback configurable and disable-able for public web deployments

## Hosaka radio direction

`hosaka radio` is the main music direction.

It is intended to cover:

- AM/FM/wideband listening
- public-domain recordings from Wikimedia Commons
- operator-provided local music files
- background playback while other windows remain active

Spotify and Kindle are modeled as alternates, not replacements.

## Kindle direction

Kindle is currently planned as an external app integration.

For Linux, the current target is compatible with package/install guidance such as:

- <https://github.com/make-install-linux/Kindle-for-ubuntu>

The goal is:

- launch through Hosaka metadata
- prefer native desktop handoff
- retain browser-safe fallback only where appropriate

## Simulcast direction

Simulcast requires actual capture and output plumbing; simply listing web apps does not implement it.

Planned role for `simulcast`:

- orchestrate one broadcast session
- coordinate capture state
- manage outbound targets
- hand off to installed platform apps where needed

No simultaneous multi-platform streaming exists yet.

## What remains to do

### Near-term

1. Add actual launch bridges for external apps from Electron
2. Add capability detection for installed apps
3. Add disable-for-web policy checks in runtime code, not just metadata
4. Add `hosaka radio` implementation for local/public-domain playback first
5. Add Kindle/Spotify/Discord launch flows behind host checks

### After that

1. Add real device/radio integrations for AM/FM/wideband
2. Add app catalog install workflows
3. Add simulcast orchestration
4. Add Instagram/TikTok external integrations
5. Add richer installer guidance for Linux and Windows nodes

## Recommended order from here

1. Finish local-first workflows with `hosaka dev`
2. Build `hosaka radio`
3. Add external app handoff for Spotify / Kindle / Discord
4. Add app catalog plumbing
5. Add simulcast later, once capture/output paths are real
