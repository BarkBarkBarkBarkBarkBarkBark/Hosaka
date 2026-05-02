# hosaka-kiosk

The canonical entrypoint to the Hosaka field terminal.

An Electron host that wraps the SPA in a single fullscreen Chromium window
and enables Electron's `<webview>` tag so the **Web** panel can render
*any* URL — github, youtube, reddit, cyberspace.online — inline, with zero
`X-Frame-Options` / CSP `frame-ancestors` grief.

Everything stays inside the one kiosk window. `window.open()` calls and
`<webview>` pop-ups are routed to the system browser (if present), so a
stray link never displaces the kiosk session.

```
kiosk/
├── package.json                ← electron dep + run scripts
├── main.js                     ← main process: kiosk window, webview policy
├── preload.js                  ← injects window.hosakaBrowserAdapter
├── scripts/dev.sh              ← one-command dev (vite + electron)
└── README.md                   ← this file
```

The SPA's `browserAdapter.ts` feature-detects `window.hosakaBrowserAdapter`.
With the preload in play it reports `mode: "native-webview"` and `WebPanel`
renders `<webview>` instead of a plain iframe. No code in the SPA branches
on runtime — the exact same bundle loads in Electron, in a plain browser,
and on Vercel.

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
| `npm run start`        | built SPA at `../hosaka/web/ui/index.html` | fullscreen    |
| `npm run start:windowed` | same as `start` but non-fullscreen       | windowed      |

Env overrides (all optional):

| Variable                   | Default                                           | Purpose                                 |
| -------------------------- | ------------------------------------------------- | --------------------------------------- |
| `HOSAKA_KIOSK_URL`         | built SPA → else `http://127.0.0.1:8421/`         | the URL Electron loads                  |
| `HOSAKA_KIOSK_FULLSCREEN`  | unset (fullscreen)                                | `0` → windowed dev mode                 |
| `HOSAKA_KIOSK_DEVTOOLS`    | unset                                             | `1` → open devtools on launch           |
| `HOSAKA_KIOSK_WIDTH`       | `1024`                                            | windowed width                          |
| `HOSAKA_KIOSK_HEIGHT`      | `600`                                             | windowed height                         |

## Edge-device boot

The Pi boots into kiosk mode by default (via `./scripts/setup_hosaka.sh`
or `HOSAKA_BOOT_MODE=kiosk ./scripts/install_hosaka.sh`). That installer:

1. Installs Node 20, Python venv, FastAPI deps.
2. Builds the SPA (`frontend/ → hosaka/web/ui/`).
3. Runs `npm install` inside `kiosk/` so the Electron binary is on disk.
4. Drops `scripts/kiosk-electron.sh` at `/usr/local/bin/hosaka-kiosk-electron`.
5. Installs the systemd units (`hosaka-webserver.service`,
   `hosaka-kiosk.service`) and enables them on `graphical.target`.

At boot:

```
graphical.target
   ├── hosaka-webserver.service   uvicorn @ 127.0.0.1:8421  (FastAPI + SPA + /api)
   └── hosaka-kiosk.service       hosaka-kiosk-electron     (Electron fullscreen
                                                             kiosk pointed at :8421)
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
