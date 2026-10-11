/** Terminal-first Electron host. Desktop/app-store bridges live in the archive. */
const { app, BrowserWindow, globalShortcut, session } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

const PID_FILE = "/run/hosaka/kiosk.pid";
const FULLSCREEN = process.env.HOSAKA_KIOSK_FULLSCREEN !== "0";
let currentUrl = process.env.HOSAKA_KIOSK_URL || "http://127.0.0.1:8421/";
let mainWindow = null;

if (process.env.HOSAKA_KIOSK_PI_FLAGS !== "0") {
  app.commandLine.appendSwitch("disable-gpu");
  app.commandLine.appendSwitch("disable-dev-shm-usage");
  app.commandLine.appendSwitch("disable-smooth-scrolling");
  app.commandLine.appendSwitch("disable-features",
    "Translate,InterestFeedContentSuggestions,CalculateNativeWinOcclusion,HardwareMediaKeyHandling,BackForwardCache");
  app.commandLine.appendSwitch("js-flags", "--max-old-space-size=128");
}
if (FULLSCREEN) app.disableHardwareAcceleration();

function showHosaka() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.setAlwaysOnTop(false);
  mainWindow.show();
  mainWindow.focus();
}

function showDesktop() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.setAlwaysOnTop(false);
  mainWindow.hide();
}

async function loadUrl(win, url) {
  try {
    await win.webContents.session.clearCache();
  } catch (error) {
    console.warn("[kiosk] could not clear HTTP cache", error);
  }
  if (win.isDestroyed()) return;
  try {
    await win.loadURL(url);
  } catch (error) {
    console.error("[kiosk] could not load Hosaka; start the local backend", error);
    win.show();
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: Number(process.env.HOSAKA_KIOSK_WIDTH) || 1024,
    height: Number(process.env.HOSAKA_KIOSK_HEIGHT) || 600,
    minWidth: 480,
    minHeight: 320,
    fullscreen: FULLSCREEN,
    kiosk: FULLSCREEN,
    // RetroArch must be able to take focus; closing it reveals this window.
    alwaysOnTop: false,
    autoHideMenuBar: true,
    backgroundColor: "#0b0d10",
    title: "Hosaka",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      backgroundThrottling: true,
    },
  });
  mainWindow = win;
  win.once("ready-to-show", () => win.show());
  win.on("closed", () => { mainWindow = null; });
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  void loadUrl(win, currentUrl);
  if (process.env.HOSAKA_KIOSK_DEVTOOLS === "1") win.webContents.openDevTools({ mode: "detach" });
}

if (!app.requestSingleInstanceLock({ hosakaKioskUrl: currentUrl })) {
  app.quit();
} else {
  app.on("second-instance", (_event, _argv, _workingDir, data) => {
    if (typeof data?.hosakaKioskUrl === "string") {
      try {
        const url = new URL(data.hosakaKioskUrl);
        if (["http:", "https:"].includes(url.protocol)) currentUrl = url.toString();
      } catch (error) {
        console.error("[kiosk] invalid retarget URL", error);
      }
    }
    if (!mainWindow || mainWindow.isDestroyed()) createWindow();
    else {
      if (mainWindow.webContents.getURL() !== currentUrl) void loadUrl(mainWindow, currentUrl);
      showHosaka();
    }
  });
  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    createWindow();
    try {
      fs.mkdirSync(path.dirname(PID_FILE), { recursive: true });
      fs.writeFileSync(PID_FILE, String(process.pid));
    } catch (error) {
      console.warn("[kiosk] could not write PID file; use Super+H to return to Hosaka", error);
    }
    process.on("SIGUSR1", showDesktop);
    process.on("SIGUSR2", showHosaka);
    if (!globalShortcut.register("Super+H", showHosaka)) console.warn("[kiosk] Super+H shortcut unavailable");
    app.on("activate", () => {
      if (!mainWindow || mainWindow.isDestroyed()) createWindow();
      else showHosaka();
    });
  }).catch(error => {
    console.error("[kiosk] startup failed", error);
    app.quit();
  });
}

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  try {
    if (fs.existsSync(PID_FILE) && fs.readFileSync(PID_FILE, "utf8").trim() === String(process.pid)) fs.unlinkSync(PID_FILE);
  } catch (error) {
    console.warn("[kiosk] could not remove PID file", error);
  }
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
