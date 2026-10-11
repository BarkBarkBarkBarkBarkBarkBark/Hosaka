# hosaka-kiosk

The default graphical host for the Hosaka field terminal.

On localhost the GUI exposes the canonical Python TUI via `/ws/tui`, with a
small Wi-Fi / Bluetooth / PlayStation Games / Flash menu. The TUI stays mounted
while the menu is open. The old desktop is retired and archived, not available
at `/?desktop=1`. The backend must be running; use `hosaka dev` to start backend, Vite,
and Electron together (the bare `npm run dev` here starts only Vite/Electron).

Electron wraps the terminal GUI in a single fullscreen Chromium window.
It has no webviews, preload bridges, app-store IPC, or automatic browser
microphone/camera grants. Pop-ups are denied. The window is not always-on-top
so RetroArch can take focus; closing a game reveals Hosaka. Super+H or
`hosaka mode console` also brings the existing terminal window back.

```
kiosk/
├── package.json                ← electron dep + run scripts
├── main.js                     ← terminal window, singleton, desktop signals
├── tests/main.test.cjs         ← native host regression tests
├── scripts/dev.sh              ← one-command dev (vite + electron)
└── README.md                   ← this file
```

The retired host and preload are preserved in
[`archive/desktop-frontend/kiosk/`](../archive/desktop-frontend/kiosk/).
Run `npm test` here to check window/singleton/signal behavior without starting
Electron.

## Local dev — one command

Repo-local shortcut:

```bash
./scripts/hosaka dev
```

This runs the same Electron host plus the Vite dev server from the repo root.

If you only want the localhost browser app, use:

```bash
./scripts/hosaka dev --web
```

```bash
cd Hosaka/kiosk
npm install            # first time only
npm run dev
```

That's it. `scripts/dev.sh`:

1. Ensures `frontend/node_modules` and `kiosk/node_modules` exist.
2. Spawns the Vite dev server on `http://localhost:5173`.
3. Waits for Vite to respond.
4. Launches Electron in windowed mode pointed at the dev server, with
   devtools on.

Edits to the SPA hot-reload inside the kiosk window via Vite HMR. Ctrl-C
in the terminal tears both down.

### Pick a target by hand

| Command                | Loads                                      | Mode          |
| ---------------------- | ------------------------------------------ | ------------- |
| `npm run dev`          | `http://localhost:5173` (vite dev server)  | windowed      |
| `npm run start:server` | `http://127.0.0.1:8421/` (FastAPI)         | fullscreen    |
| `npm run start`        | `http://127.0.0.1:8421/` (FastAPI)         | fullscreen    |
| `npm run start:windowed` | same as `start` but non-fullscreen       | windowed      |

Env overrides (all optional):

| Variable                   | Default                                           | Purpose                                 |
| -------------------------- | ------------------------------------------------- | --------------------------------------- |
| `HOSAKA_KIOSK_URL`         | `http://127.0.0.1:8421/`                         | the URL Electron loads                  |
| `HOSAKA_KIOSK_FULLSCREEN`  | unset (fullscreen)                                | `0` → windowed dev mode                 |
| `HOSAKA_KIOSK_DEVTOOLS`    | unset                                             | `1` → open devtools on launch           |
| `HOSAKA_KIOSK_WIDTH`       | `1024`                                            | windowed width                          |
| `HOSAKA_KIOSK_HEIGHT`      | `600`                                             | windowed height                         |

## Edge-device boot

New cyberdecks default to the terminal GUI. To opt into the plain TUI instead,
use `HOSAKA_DISPLAY_MODE=tui ./scripts/install_hosaka.sh`;
`hosaka display tui|gui` persists the choice for the next graphical login.
The appliance installer:

1. Installs Node 20, Python venv, FastAPI deps.
2. Builds the SPA (`frontend/ → hosaka/web/ui/`).
3. Installs Electron only when GUI display mode is selected.
4. Drops `scripts/kiosk-electron.sh` at `/usr/local/bin/hosaka-kiosk-electron`.
5. Enables the webserver; the LXQt/Openbox session launcher chooses TUI or GUI.
   The kiosk systemd unit remains disabled to avoid duplicate GUI supervisors.

`hosaka update` pulls/builds/deploys in an independent, memory-limited systemd
job and refreshes installed launchers/autostart. The first deployment migrates
old boot preferences to GUI; later explicit display choices are preserved.
See the [Pi update bootstrap](../README.md#one-command-raspberry-pi-updates)
for installations that still have the old CLI.

At boot:

```
hosaka-webserver.service   uvicorn @ 127.0.0.1:8421
graphical login            TUI (default) or Electron terminal + menu (opt-in)
```

`hosaka-kiosk-electron` waits on `/api/health`, biases the process HIGH
for the OOM killer (SSH keeps priority), then `exec`s into the Electron
binary with `HOSAKA_KIOSK_URL=http://127.0.0.1:8421/`. The SPA has
first-class access to `/api/*` because it's same-origin.

### Chromium fallback

If Electron deps aren't installed yet (fresh clone on the Pi, pre-`setup`
state), the openbox autostart falls back to the old `chromium --kiosk`
path — the SPA still loads, you just lose `<webview>` mode and the Web
panel reverts to iframes with the "⚠ page blank?" disclosure.

Run `cd ~/Hosaka/kiosk && npm install` on the Pi to switch back to
Electron on the next reboot (or `sudo systemctl restart hosaka-kiosk`).

## Security notes

- `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` in
  the main window — the SPA has no access to Node APIs beyond what
  `preload.js` exposes via `contextBridge`.
- `<webview>` uses a separate partition (`persist:hosaka-browser`), so
  cookies from sites the operator browses don't leak into the SPA's
  own session.
- Any `window.open()` call (from the SPA or from a `<webview>`) is
  denied and handed to `shell.openExternal`. On a headless Pi with no
  other browser, those calls silently no-op.

## What happens off-device

Deploy the SPA anywhere else (Vercel field-terminal, a plain browser, a
dev laptop opening Vite directly) and `window.hosakaBrowserAdapter` is
absent. The adapter reports `mode: "web-fallback"` and `WebPanel` renders
a plain iframe. Sites that refuse framing show the "⚠ page blank?"
disclosure. The "native" experience is an Electron-or-nothing feature —
that's fine, because on the edge device Electron is always there.
