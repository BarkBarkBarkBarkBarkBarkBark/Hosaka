# Hosaka UI Control Surface

Hosaka is moving from a tab-only shell toward a voice-first, launcher-oriented
control model. This document explains the new renderer UI command layer,
describes the processes needed to make the experience seamless on new
machines, and breaks the migration into small implementation steps.

## What shipped in this pass

- A canonical command spec in [docs/hosaka_ui_commands.yaml](docs/hosaka_ui_commands.yaml)
- A renderer-side dispatcher in [frontend/src/ui/hosakaUi.ts](frontend/src/ui/hosakaUi.ts)
- Shell refactors in [frontend/src/shell/HosakaShell.ts](frontend/src/shell/HosakaShell.ts)
  so existing slash commands reuse the new command layer instead of
  duplicating `CustomEvent` dispatch logic
- A global bridge at `window.hosakaUI` for renderer-local automation and future
  agent / voice use
- An app registry that now also records Electron-first host preference and
  install policy for planned integrations

## Host policy now

Hosaka is Electron-first on-device.

That means:

- prefer Electron whenever native desktop capability matters
- keep browser/web fallback where it is safe and useful
- model external desktop apps explicitly in the registry instead of assuming
  iframe/embed behavior
- keep unsupported flows disable-able for hosted/public web builds

## Core idea

The agent should not click the interface.

Instead, it should issue typed intents such as:

- `ui.open_panel(target=todo)`
- `ui.open_settings()`
- `ui.show_document(slug=beacon_protocol)`
- `ui.search_books(query="gps")`
- `ui.open_web_preset(preset=reddit)`

The renderer then maps those intents onto the current event bus today, and can
later map the same intents onto Electron windows, BrowserViews, drawers, or
launcher tiles.

## Why this matters for end users

The new-machine experience should feel like this:

1. unbox Hosaka
2. land in a voice-first home or transcript surface
3. say “show me my todo list”
4. Hosaka opens the right UI without the operator learning the tab model first

That requires a stable control surface behind the UI.

## Processes required to make this seamless

### 1. Canonical command vocabulary

**Current state**

- The shell has slash commands, but many of them directly dispatch raw
  `CustomEvent`s from [frontend/src/shell/HosakaShell.ts](frontend/src/shell/HosakaShell.ts).
- Commands are partially de-duplicated, but aliases like `/reddit` and `/discord`
  are still implemented as custom branches.

**Goal state**

- All UI control flows through canonical `ui.*` commands.
- Slash commands, voice tools, launcher actions, and future agent tools all use
  the same command vocabulary.

**Atomized steps**

1. Define canonical commands in YAML
2. Mark which ones are shipping, compatibility, or planned
3. Group old slash commands under canonical intents
4. Keep aliases, but map them onto one canonical action

### 2. Surface registry

**Current state**

- Surface names are scattered across `App.tsx`, `HosakaShell.ts`, and
  `browserAdapter.ts`.
- Some surfaces exist in the app but not in the shell command set.

**Goal state**

- One registry defines launchable surfaces, aliases, status, and host policy.

**Atomized steps**

1. Centralize `surface_id` values in the command spec
2. Track aliases like `tasks -> todo`, `browser -> web`
3. Mark planned surfaces like `gps`, `music`, `tool_directory`
4. Reuse the registry in shell, voice, and launcher code

### 3. Renderer dispatcher

**Current state**

- The event bus works, but the logic is duplicated.
- Different call sites know too much about event names.

**Goal state**

- A renderer module executes canonical UI commands and hides event details.

**Atomized steps**

1. Add [frontend/src/ui/hosakaUi.ts](frontend/src/ui/hosakaUi.ts)
2. Expose `executeHosakaUiCommand()`
3. Keep `CustomEvent` dispatch as a compatibility layer inside that module
4. Move shell code to call the dispatcher
5. Expose the bridge on `window.hosakaUI`

### 4. Voice / agent integration

**Current state**

- Voice tools are server-oriented and do not yet have a dedicated renderer UI
  command path.
- The browser can control local transcript and panels, but there is no unified
  tool for “show gps” or “open todo”.

**Goal state**

- Voice and agent actions can call `ui.*` commands through a safe local bridge.

**Atomized steps**

1. Add a browser-local UI tool that calls `window.hosakaUI.execute(...)`
2. Hide or disable those tools in headless contexts with no renderer
3. Give the model a small list of canonical surface ids and aliases
4. Log and confirm UI actions in transcript output

### 5. Host policy: tab vs window

**Current state**

- Browser mode and Electron both effectively route UI actions into the SPA.
- There is no multi-window policy yet.

**Goal state**

- The same command can open a tab in browser mode and a native window in
  Electron where appropriate.
- External desktop integrations should be capability-checked handoffs, not
  assumed in-panel apps.

**Atomized steps**

1. Keep `ui.open_panel` working everywhere
2. Introduce `ui.open_surface` as the host-aware successor
3. Add per-surface policy: `tab`, `window`, `auto`
4. Promote selected surfaces to native windows in Electron
5. Keep browser builds on tab fallback

### 6. Launcher / tool directory

**Current state**

- The top dock is the main navigation primitive.
- There is no first-class launcher surface yet.

**Goal state**

- A voice-friendly home / launcher shows launchable tools and app surfaces.

**Atomized steps**

1. Create a `tool_directory` surface in the registry
2. Make it searchable and alias-aware
3. Route voice intents like “open browser” through it when useful
4. Use it as the onboarding home for new installs

## Current state summary

The project already has strong primitives:

- `CustomEvent`-based cross-panel control
- shell commands as semantic actions
- a browser adapter abstraction
- an Electron host

What was missing was the layer that turns those pieces into one stable control
surface. The new dispatcher is that first step.

## Goal state summary

The finished model should look like this:

1. operator speaks or types an intent
2. Hosaka resolves it to a canonical `ui.*` command
3. renderer executes it through one dispatcher
4. host decides whether that becomes a tab, card, or native window
5. transcript confirms what changed

## What is implemented vs planned

### Implemented now

- canonical command YAML
- surface alias resolution
- renderer dispatcher for current shipping commands
- shell migration onto the dispatcher
- global bridge for future consumers

### Planned next

- direct voice / agent use of `window.hosakaUI`
- launcher / tool directory surface
- native Electron window routing for selected surfaces
- new surfaces such as GPS and music
- external integrations such as Spotify, Kindle, Discord, and Hosaka Radio

## Recommended next implementation steps

1. add a small renderer-side “UI tool” for voice / agent use
2. add `ui.open_surface` execution rules for Electron
3. add a launcher / home surface
4. add `gps` as the first new non-tabbed app candidate
5. log UI actions into transcript / shell output for trust and observability

## Design rule to keep

Do not automate clicks as the primary path.

Clicks are brittle. Intents are durable.
