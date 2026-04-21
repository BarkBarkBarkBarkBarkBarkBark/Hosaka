/**
 * Hosaka kiosk — Electron main process.
 *
 * The single, canonical entrypoint to the Hosaka SPA. Wraps the app in a
 * native Chromium window and turns on Electron's <webview> tag so the
 * browser panel can mount a real webview (no X-Frame-Options / CSP grief).
 *
 * Everything stays inside this one window; `window.open()` and <webview>
 * pop-ups are routed to the system browser (if any) via `shell.openExternal`
 * so the kiosk session is never displaced by a stray tab.
 *
 * URL resolution (first match wins):
 *   1. $HOSAKA_KIOSK_URL (explicit override — used by dev + systemd)
 *   2. The built SPA at ../hosaka/web/ui/index.html, if present
 *   3. http://127.0.0.1:8421 (assumes hosaka-webserver.service is up)
 *
 * On the Pi the launcher (scripts/kiosk-electron.sh) sets
 * HOSAKA_KIOSK_URL=http://127.0.0.1:8421 and only starts us after the
 * FastAPI health check passes, so /api calls from the SPA just work.
 *
 * Env:
 *   HOSAKA_KIOSK_URL         override — any URL or file:// path
 *   HOSAKA_KIOSK_FULLSCREEN  "0" → windowed dev mode; anything else → kiosk
 *   HOSAKA_KIOSK_WIDTH       window width when not fullscreen (default 1024)
 *   HOSAKA_KIOSK_HEIGHT      window height when not fullscreen (default 600)
 *   HOSAKA_KIOSK_DEVTOOLS    "1" → open devtools on launch (dev only)
 */
const { app, BrowserWindow, session, shell } = require("electron");
const path = require("path");
const fs = require("fs");

function resolveStartUrl() {
  if (process.env.HOSAKA_KIOSK_URL) return process.env.HOSAKA_KIOSK_URL;
  const built = path.resolve(__dirname, "..", "hosaka", "web", "ui", "index.html");
  if (fs.existsSync(built)) return `file://${built}`;
  // Final fallback: FastAPI should already be serving the SPA at :8421.
  return "http://127.0.0.1:8421/";
}

const START_URL = resolveStartUrl();
const FULLSCREEN = process.env.HOSAKA_KIOSK_FULLSCREEN !== "0";
const DEVTOOLS = process.env.HOSAKA_KIOSK_DEVTOOLS === "1";
const WIDTH = Number(process.env.HOSAKA_KIOSK_WIDTH) || 1024;
const HEIGHT = Number(process.env.HOSAKA_KIOSK_HEIGHT) || 600;

// Pi 3B has 1 GB of RAM shared with the GPU; turning off hardware accel keeps
// Electron from fighting Chromium's flaky GLES stack on that board. We only
// flip the switch when fullscreen is on — locally you want the compositor.
if (FULLSCREEN) {
  app.disableHardwareAcceleration();
}

// Single-instance lock — if the operator somehow runs `electron .` a second
// time, focus the existing window instead of spawning a second kiosk.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: WIDTH,
    height: HEIGHT,
    minWidth: 480,
    minHeight: 320,
    fullscreen: FULLSCREEN,
    kiosk: FULLSCREEN,
    autoHideMenuBar: true,
    backgroundColor: "#0b0d10",
    title: "Hosaka",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      webviewTag: true,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      // Save ~20-40 MB of RAM on the Pi by disabling the background throttler's
      // cache for invisible frames — the kiosk only has one window anyway.
      backgroundThrottling: false,
    },
  });

  win.once("ready-to-show", () => win.show());
  win.loadURL(START_URL);
  if (DEVTOOLS) win.webContents.openDevTools({ mode: "detach" });

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url).catch(() => { /* non-fatal */ });
    return { action: "deny" };
  });

  // <webview> pop-ups follow the same policy — deny new windows, hand the
  // URL to the system browser if the operator has one installed.
  win.webContents.on("did-attach-webview", (_event, wc) => {
    wc.setWindowOpenHandler(({ url }) => {
      shell.openExternal(url).catch(() => { /* non-fatal */ });
      return { action: "deny" };
    });
  });
}

app.whenReady().then(() => {
  // The SPA uses the default session for fetches; <webview> uses its own
  // partition so cookies/storage for external sites don't leak into it.
  session.fromPartition("persist:hosaka-browser");
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
