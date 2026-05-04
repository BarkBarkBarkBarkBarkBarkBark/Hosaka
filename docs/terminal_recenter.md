You are refactoring the Hosaka repo into a truly terminal-first cyberdeck experience.

Repo: BarkBarkBarkBarkBarkBarkBark/Hosaka

Goal:
Hosaka must boot visually into the terminal as the primary interaction surface. All other GUI features must be launched from terminal commands or from a small hidden/expandable menu. Preserve existing working pathways where possible, but strategically sever or demote desktop/tab/landing-page patterns that compete with the terminal.

Core product rule:
The terminal determines what is possible. The GUI only renders surfaces requested by terminal commands, menu actions, or orb/device buttons.

Current useful seams to preserve:

* frontend/src/App.tsx already lazy-loads panels and renders FloatingOrb.
* frontend/src/ui/appRegistry.ts is the source of truth for apps, aliases, host preference, install policy, and launchability.
* frontend/src/ui/windowState.ts persists active app/open windows/chrome collapsed state.
* frontend/src/ui/hosakaUi.ts already bridges UI commands to window/app events.
* frontend/src/panels/TerminalPanel.tsx owns xterm and HosakaShell.
* frontend/src/shell/HosakaShell.ts handles slash commands.
* frontend/src/panels/DiagnosticsPanel.tsx already has mic meter, camera preview, browser device enumeration, and /api/v1/diag/snapshot polling.
* frontend/src/panels/DevicePanel.tsx already stores mic/cam/speaker preferences in localStorage.
* hosaka/web/diag_api.py already exposes the shared diagnostics API used by SPA, /device page, and CLI.

High-level refactor:

1. Make terminal the default active surface.

   * In frontend/src/ui/windowState.ts, INITIAL_WINDOWS_DOC should default activeAppId to "terminal".
   * Home/desktop should become optional and secondary, not the boot experience.
   * The terminal should fill the stage by default.
   * The top chrome should be minimal: hamburger/menu, orb, terminal, device mode.
   * The dock/window strip should be hidden by default or moved into an expandable chevron/menu.

2. Introduce a terminal-led overlay/window manager.

   * Do not try to render React widgets inside xterm itself.
   * Keep xterm as the primary surface.
   * Commands should dispatch structured UI events that open floating overlay windows above the terminal.
   * Add a lightweight OverlayStack/SurfaceWindow system that can render small popups with title bar, close button, optional pin/minimize, and low-memory unmount behavior.
   * Overlay windows should be small, draggable only if cheap/simple; do not add heavy dependencies.
   * Overlay state should live in the existing windows/app state model or a compatible extension of it.
   * Persist only lightweight state: surface id, open/closed, position, size, pinned, lastFocusedAt, minimal snapshot.

3. Centralize command routing.

   * Extend frontend/src/ui/hosakaUi.ts into the single browser-side UI command bridge.
   * Add commands such as:

     * ui.open_surface
     * ui.close_surface
     * ui.toggle_menu
     * ui.toggle_orb
     * ui.launch_app
     * ui.device_check
     * ui.device_select
     * ui.show_diagnostics
   * HosakaShell should not directly know component internals.
   * HosakaShell slash commands should parse text and call executeHosakaUiCommand.
   * Keep backwards-compatible aliases: /devices, /device, /diagnostics, /voice, /terminal, /apps, /store, /launch.

4. Implement terminal-first commands.

   * /launch <app>

     * Resolve app by appRegistry aliases.
     * If built-in panel: open as overlay or focused surface depending on metadata.
     * If external app/Flatpak: call existing flatpak/app backend if available.
     * Always print a short terminal confirmation with resolved app, host, and status.
   * /device

     * Open compact diagnostics overlay.
   * /device check mic

     * Open a focused DeviceCheckWindow for audio input.
     * Show browser permission state, enumerated audioinput devices, selected mic, live RMS/level meter, getUserMedia error text, and server-side audio diagnostics from /api/v1/diag/snapshot.
     * Include actions: grant permission, refresh devices, set selected mic, start/stop meter, copy diagnostic JSON.
   * /device check cam

     * Open camera check overlay with browser camera list, selected camera, preview, getUserMedia errors, server video diagnostics.
   * /device check spk or /device check speaker

     * Open speaker/audio output overlay.
     * Show audiooutput devices if Chromium/Electron supports enumerateDevices and setSinkId.
     * Include simple test tone button.
   * /orb

     * Toggle or focus orb mode.
     * Orb must always remain visible in a corner, even when inactive.
   * /menu

     * Toggle compact multi-tier menu.
   * /terminal

     * Refocus terminal and close/demote non-pinned overlays if needed.

5. Refactor DiagnosticsPanel into reusable diagnostic primitives.

   * Extract reusable hooks/components:

     * useBrowserDevices
     * useAudioMeter
     * useWebcamPreview
     * DeviceList
     * AudioMeter
     * CameraPreview
     * DiagnosticJsonBlock
   * Reuse these in DiagnosticsPanel and the new DeviceCheckWindow.
   * Keep existing DiagnosticsPanel functional to avoid breaking current routes.
   * Do not duplicate getUserMedia logic across VoicePanel, DiagnosticsPanel, and DeviceCheckWindow if it can be shared safely.

6. Respect memory constraints.

   * Preserve React.lazy panel loading.
   * Do not eagerly mount all panels.
   * Keep terminal mounted.
   * Mount overlay content only when opened.
   * Stop media streams when overlay closes or becomes inactive.
   * Keep xterm scrollback at the existing lightweight value unless there is a strong reason to change it.
   * Avoid new UI libraries.
   * Avoid animation libraries.
   * Avoid heavy state managers.
   * Use existing React state, localStorage, and current synced doc model.
   * No broad dependency additions unless absolutely necessary.

7. Strategic severing/demotion.

   * Demote desktop/home/landing page from default boot path.
   * Keep it accessible via /home or menu, but it should not define the product.
   * Remove or hide redundant dock/tab UI where it competes with terminal-first usage.
   * Keep appRegistry as source of truth instead of scattering app metadata across menus, buttons, and command handlers.
   * If there are multiple ways to launch the same thing, route them through the same command bridge.

8. UI requirements.

   * Visual style: old-school 90s hacker instrument windows, but clean and readable.
   * Terminal should feel like command magic.
   * Overlay windows should feel like little diagnostic instruments, not web pages.
   * The orb is always visible in a corner.
   * Main visible buttons:

     * hamburger/menu
     * orb
     * terminal
     * device mode
   * Chevron/menu may reveal advanced multi-tier options, but it should stay out of the way.

9. Device troubleshooting must be agent-friendly.

   * The same diagnostic data shown to the user should be exposed as JSON for an agent.
   * Add a compact “copy diagnostics” or “agent context” payload for mic/cam/speaker checks.
   * The payload should include:

     * browser permission state
     * enumerated browser devices
     * selected localStorage device ids
     * getUserMedia success/failure/error name/message
     * current RMS/level if mic test is running
     * relevant /api/v1/diag/snapshot.peripherals section
     * OS tool availability: pactl, arecord, aplay, v4l2-ctl where present
   * Do not hide raw errors. The point is to help the agent fix the damn mic.

10. Acceptance criteria.

* App boots into terminal-first layout.
* /device check mic opens a compact overlay with live audio meter and device list.
* /device check cam opens compact camera preview overlay.
* /device check spk opens speaker selection/test overlay where supported.
* /launch terminal, /launch docs, /launch voice, /launch music, /launch app-store work via appRegistry aliases.
* Existing DiagnosticsPanel still works.
* Existing VoicePanel still works.
* Existing FloatingOrb still renders globally.
* npm run build succeeds.
* npm run typecheck succeeds if currently supported.
* No heavy dependency additions.
* No breaking changes to /api/v1/diag/snapshot.
* Terminal commands print useful confirmations/errors rather than silently changing UI.

Implementation order:

1. Inspect current App.tsx, windowState.ts, appRegistry.ts, hosakaUi.ts, HosakaShell.ts, DiagnosticsPanel.tsx, DevicePanel.tsx, and diag_api.py.
2. Add the overlay/window primitives.
3. Change initial state so terminal is default.
4. Extend hosakaUi command bridge.
5. Wire HosakaShell slash commands into the bridge.
6. Extract diagnostic hooks from DiagnosticsPanel.
7. Build DeviceCheckWindow for mic/cam/speaker.
8. Minimize/hide competing dock/desktop chrome.
9. Test build/typecheck.
10. Leave a short implementation report listing changed files, retained compatibility paths, severed/demoted UI paths, and remaining TODOs.

---

## What shipped (May 2026)

Boot + chrome:

* `frontend/src/ui/windowState.ts` — `INITIAL_WINDOWS_DOC.activeAppId = "terminal"`, `openAppIds = ["terminal"]`, `chromeCollapsed = true`.
* `frontend/src/ui/appRegistry.ts` — `terminal` marked `closable: false` so it always stays mounted.
* `frontend/src/App.tsx` — fallback surface is `terminal` (not `home`); listens for `hosaka:toggle-menu`, `hosaka:toggle-chrome`, `hosaka:focus-terminal`; new `.hosaka-quickbar` (terminal / devices / orb) next to the hamburger.
* `frontend/src/styles/app.css` — when `.hosaka-shell--chrome-collapsed`, the launchbar + window strip + footer are hidden; quickbar styling added.

Overlay / instrument system:

* `frontend/src/ui/overlayState.ts` — `OverlaysDoc`, surface ids, default geometry, event names.
* `frontend/src/sync/store.ts` — added `"overlays"` DocName.
* `frontend/src/components/SurfaceWindow.tsx` — 90s-instrument floating window with pointer-events drag, pin, close. No new deps.
* `frontend/src/components/OverlayStack.tsx` — shell-root overlay renderer; children are `React.lazy` so media code ships only when opened; reacts to `hosaka:overlay-open/close/close-all/focus`.

Shared diagnostic primitives:

* `frontend/src/panels/diagPrimitives.tsx` — exported `useBrowserDevices`, `useAudioMeter` (adds peak + liveRef), `useWebcamPreview`, plus `AudioMeter` (segmented VU), `DeviceList`, `DiagnosticJsonBlock`, `statusClass`, `fetchDiagSnapshot`, `buildDeviceAgentPayload`, `copyDeviceAgentPayloadToClipboard`.
* `frontend/src/panels/DiagnosticsPanel.tsx` — slimmed to import the shared primitives (same UX).

Instrument windows (`frontend/src/panels/overlays/`):

* `MicCheckWindow.tsx` — segmented dB meter, RMS + dBFS readout, audioinput dropdown, permission + getUserMedia error surface, copy diagnostics.
* `CamCheckWindow.tsx` — ~480×270 @ ~15 fps compressed preview, videoinput dropdown, copy diagnostics.
* `SpkCheckWindow.tsx` — audiooutput dropdown wired through `setSinkId` (falls back to system default when unsupported), 440 Hz 0.4 s test tone, copy diagnostics.
* `DiagOverlay.tsx` — peripherals pill strip + network primary + memory + "open full devices panel" link.

Command bridge:

* `frontend/src/ui/hosakaUi.ts` — added `ui.close_surface`, `ui.toggle_menu`, `ui.toggle_orb`, `ui.toggle_chrome`, `ui.focus_terminal`, `ui.launch_app`, `ui.device_check`, `ui.device_select`, `ui.show_diagnostics`. `ui.open_surface` now accepts `preferredContainer: "overlay"`. Bridge exposes `snapshotDeviceAgentPayload(kind)` on `window.hosakaUI` for agents.

Terminal commands:

* `frontend/src/shell/HosakaShell.ts` — new `/device check mic|cam|spk`, `/device list`, bare `/device` opens the overlay, legacy probe kept as `/device probe`; new `/menu`; `/orb` toggles the voice orb (art still available via `/orb art`); `/terminal` now calls `ui.focus_terminal` and closes non-pinned overlays.
* `frontend/src/shell/commands.ts` — help table updated to reflect the new device subcommands, `/menu`, and `/terminal` semantics.

Preserved:

* `DiagnosticsPanel`, `DevicePanel`, `VoicePanel`, `FloatingOrb`, `/api/v1/diag/snapshot`, `/api/v1/*` contracts, React.lazy panels, xterm scrollback 1500.
* Backwards-compatible aliases: `/devices`, `/device`, `/diagnostics`, `/voice`, `/terminal`, `/apps`, `/store`, `/launch`, `/messages`, `/home`, `/desktop`, `/reading`, `/video`, `/games`, `/wiki`.

Severed / demoted:

* `home` no longer in boot `openAppIds`. Still reachable via `/home`, the menu, or `/launch home`.
* Default chrome hides launchbar + tab strip; operator expands via the chevron or `/menu`.

Remaining TODOs:

* Resize handle on `SurfaceWindow` (currently size is doc-controlled but not user-resizable).
* Minimize state for overlays (schema has `pinned` already; a minimized flag is the obvious next step).
* `/api/v1/diag/snapshot` could surface `setSinkId` support explicitly so the spk check window can report it server-side too.
