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
const { app, BrowserWindow, net, session, shell, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const YAML = require("yaml");

const APPS_ROOT = path.resolve(__dirname, "..", "hosaka-apps");
const APPS_REGISTRY_PATH = path.join(APPS_ROOT, "registry.yaml");
const APPS_DIR = path.join(APPS_ROOT, "apps");

// Mock mode short-circuits every flatpak shell-out so dev on macOS (or any
// host without flatpak) gets realistic, deterministic responses instead of
// "flatpak is not installed". Auto-on for darwin so first-run dev "just
// works"; explicit `HOSAKA_FAKE_FLATPAK=0` forces real shell-outs even
// there; `=1` forces mock everywhere (useful for CI on Linux).
function fakeFlatpakEnabled() {
  const raw = String(process.env.HOSAKA_FAKE_FLATPAK ?? "").trim().toLowerCase();
  if (raw === "1" || raw === "true" || raw === "yes") return true;
  if (raw === "0" || raw === "false" || raw === "no") return false;
  return process.platform === "darwin" || process.platform === "win32";
}

// Tracks which flatpak ids the mock layer pretends are installed so the
// install → status → launch flow tells a coherent story across IPC calls.
const MOCK_INSTALLED = new Set();

// Hard cap on flatpak install time. The IPC promise was previously
// unbounded; a stuck install would lock the renderer forever.
const FLATPAK_INSTALL_TIMEOUT_MS = 5 * 60 * 1000;
const FLATPAK_DEFAULT_TIMEOUT_MS = 20 * 1000;

function logHosakaApps(message, extra) {
  if (extra === undefined) {
    console.log(`[hosaka-apps] ${message}`);
    return;
  }
  console.log(`[hosaka-apps] ${message}`, extra);
}

function normalizeAppToken(raw) {
  return String(raw ?? "").trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-");
}

function readYamlFile(filePath) {
  return YAML.parse(fs.readFileSync(filePath, "utf8"));
}

function readAppsRegistry() {
  try {
    if (!fs.existsSync(APPS_REGISTRY_PATH)) {
      return {
        backends: {
          flatpak: {
            remote: {
              name: "flathub",
              url: "https://flathub.org/repo/flathub.flatpakrepo",
            },
          },
        },
      };
    }
    return readYamlFile(APPS_REGISTRY_PATH) || {};
  } catch (error) {
    logHosakaApps("failed to read registry", error);
    return {
      backends: {
        flatpak: {
          remote: {
            name: "flathub",
            url: "https://flathub.org/repo/flathub.flatpakrepo",
          },
        },
      },
    };
  }
}

function toCommand(value) {
  return Array.isArray(value) ? value.map((entry) => String(entry)) : [];
}

function normalizeManifest(rawManifest) {
  if (!rawManifest || typeof rawManifest !== "object") return null;
  const manifest = rawManifest;
  const id = normalizeAppToken(manifest.id);
  const flatpakId = String(manifest.flatpak_id ?? "").trim();
  const installCommand = toCommand(manifest.install?.command);
  const launchCommand = toCommand(manifest.launch?.command);
  if (!id || !flatpakId || installCommand.length === 0 || launchCommand.length === 0) {
    return null;
  }
  const aliases = Array.isArray(manifest.aliases)
    ? manifest.aliases.map((alias) => normalizeAppToken(alias)).filter(Boolean)
    : [];
  return {
    id,
    name: String(manifest.name ?? id),
    backend: String(manifest.backend ?? "flatpak"),
    flatpakId,
    installCommand,
    launchCommand,
    aliases: Array.from(new Set([id, ...aliases])),
  };
}

function readAppManifests() {
  if (!fs.existsSync(APPS_DIR)) return [];
  return fs.readdirSync(APPS_DIR)
    .filter((entry) => /\.ya?ml$/i.test(entry))
    .map((entry) => {
      const filePath = path.join(APPS_DIR, entry);
      try {
        return normalizeManifest(readYamlFile(filePath));
      } catch (error) {
        logHosakaApps(`failed to read manifest ${entry}`, error);
        return null;
      }
    })
    .filter(Boolean);
}

function resolveManifest(rawAppId) {
  const token = normalizeAppToken(rawAppId);
  return readAppManifests().find((manifest) => manifest.id === token || manifest.aliases.includes(token)) ?? null;
}

function collectDetails(result) {
  const details = [];
  if (result.stdout) details.push(...result.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
  if (result.stderr) details.push(...result.stderr.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
  return details.slice(-10);
}

function runCommand(file, args, options = {}) {
  const timeoutMs = Math.max(0, Number(options.timeoutMs) || FLATPAK_DEFAULT_TIMEOUT_MS);
  return new Promise((resolve) => {
    const child = spawn(file, args, {
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (payload) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(payload);
    };
    const timer = timeoutMs > 0
      ? setTimeout(() => {
          try { child.kill("SIGTERM"); } catch (_e) { /* ignore */ }
          finish({ ok: false, code: null, stdout, stderr: stderr + `\n[hosaka-apps] timed out after ${timeoutMs}ms`, timedOut: true });
        }, timeoutMs)
      : null;
    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
    child.on("error", (error) => finish({ ok: false, code: null, stdout, stderr, error }));
    child.on("close", (code) => finish({ ok: code === 0, code, stdout, stderr }));
  });
}

async function flatpakAvailable() {
  if (fakeFlatpakEnabled()) {
    return { ok: true, mocked: true, result: { ok: true, code: 0, stdout: "Flatpak 1.99.0 (mocked)\n", stderr: "" } };
  }
  const result = await runCommand("flatpak", ["--version"]);
  return { ok: result.ok, result };
}

function getFlatpakRemoteConfig() {
  const registry = readAppsRegistry();
  return {
    name: registry.backends?.flatpak?.remote?.name || "flathub",
    url: registry.backends?.flatpak?.remote?.url || "https://flathub.org/repo/flathub.flatpakrepo",
  };
}

async function flathubConfigured(remoteName) {
  if (fakeFlatpakEnabled()) {
    return { ok: true, exists: true, result: { ok: true, code: 0, stdout: `${remoteName}\n`, stderr: "" } };
  }
  const result = await runCommand("flatpak", ["remotes", "--columns=name"]);
  if (!result.ok) {
    return { ok: false, exists: false, result };
  }
  const names = result.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return { ok: true, exists: names.includes(remoteName), result };
}

async function ensureFlathubRemote() {
  const remote = getFlatpakRemoteConfig();
  const existing = await flathubConfigured(remote.name);
  if (existing.ok && existing.exists) {
    return { ok: true, exists: true, details: [] };
  }
  const addResult = await runCommand("flatpak", [
    "remote-add",
    "--if-not-exists",
    remote.name,
    remote.url,
  ]);
  if (!addResult.ok) {
    return {
      ok: false,
      exists: false,
      actionableCommand: `flatpak remote-add --if-not-exists ${remote.name} ${remote.url}`,
      details: collectDetails(addResult),
    };
  }
  return {
    ok: true,
    exists: true,
    details: collectDetails(addResult),
  };
}

async function flatpakInstalled(flatpakId) {
  if (fakeFlatpakEnabled()) {
    const installed = MOCK_INSTALLED.has(flatpakId);
    return { installed, result: { ok: installed, code: installed ? 0 : 1, stdout: installed ? `Ref: app/${flatpakId}/x86_64/stable\n` : "", stderr: installed ? "" : `error: ${flatpakId} not installed\n` } };
  }
  const result = await runCommand("flatpak", ["info", flatpakId]);
  return { installed: result.ok, result };
}

async function getAppStatus(appId) {
  const manifest = resolveManifest(appId);
  if (!manifest) {
    return {
      ok: false,
      manifestFound: false,
      message: `app not found: ${appId}`,
      host: "electron",
    };
  }

  const flatpak = await flatpakAvailable();
  if (!flatpak.ok) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      flatpakAvailable: false,
      host: "electron",
      message: "flatpak is not installed on this system.",
      actionableCommand: "install flatpak first, then retry /install <app>",
      details: collectDetails(flatpak.result),
    };
  }

  const remote = getFlatpakRemoteConfig();
  const remoteState = await flathubConfigured(remote.name);
  const installed = await flatpakInstalled(manifest.flatpakId);
  return {
    ok: true,
    appId: manifest.id,
    manifestFound: true,
    installed: installed.installed,
    flatpakAvailable: true,
    flathubConfigured: remoteState.exists,
    host: "electron",
    message: `${manifest.name} is ${installed.installed ? "installed" : "not installed"}.`,
    details: [],
  };
}

async function installApp(appId) {
  const manifest = resolveManifest(appId);
  if (!manifest) {
    return {
      ok: false,
      manifestFound: false,
      message: `app not found: ${appId}`,
      host: "electron",
    };
  }
  const flatpak = await flatpakAvailable();
  if (!flatpak.ok) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      flatpakAvailable: false,
      host: "electron",
      message: "flatpak is not installed on this system.",
      actionableCommand: "install flatpak first, then retry /install <app>",
      details: collectDetails(flatpak.result),
    };
  }
  const remote = await ensureFlathubRemote();
  if (!remote.ok) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      flatpakAvailable: true,
      flathubConfigured: false,
      host: "electron",
      message: "could not configure the Hosaka app source.",
      actionableCommand: remote.actionableCommand,
      details: remote.details,
    };
  }
  const installed = await flatpakInstalled(manifest.flatpakId);
  if (installed.installed) {
    return {
      ok: true,
      appId: manifest.id,
      manifestFound: true,
      installed: true,
      flatpakAvailable: true,
      flathubConfigured: true,
      host: "electron",
      message: `${manifest.name} is already installed.`,
      details: [`install command: ${manifest.installCommand.join(" ")}`],
    };
  }
  logHosakaApps(`installing ${manifest.id}`, manifest.installCommand);
  const [file, ...args] = manifest.installCommand;
  const result = fakeFlatpakEnabled()
    ? (MOCK_INSTALLED.add(manifest.flatpakId), { ok: true, code: 0, stdout: `[mock] installed ${manifest.flatpakId}\n`, stderr: "" })
    : await runCommand(file, args, { timeoutMs: FLATPAK_INSTALL_TIMEOUT_MS });
  if (!result.ok) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      installed: false,
      flatpakAvailable: true,
      flathubConfigured: true,
      host: "electron",
      message: `install failed for ${manifest.name}.`,
      details: [`install command: ${manifest.installCommand.join(" ")}`, ...collectDetails(result)],
    };
  }
  return {
    ok: true,
    appId: manifest.id,
    manifestFound: true,
    installed: true,
    flatpakAvailable: true,
    flathubConfigured: true,
    host: "electron",
    message: `installed ${manifest.name}.`,
    details: [`install command: ${manifest.installCommand.join(" ")}`, ...collectDetails(result)],
  };
}

async function spawnDetached(file, args) {
  return new Promise((resolve) => {
    const child = spawn(file, args, {
      shell: false,
      detached: true,
      stdio: "ignore",
    });
    child.once("error", (error) => resolve({ ok: false, error }));
    child.once("spawn", () => {
      child.unref();
      resolve({ ok: true });
    });
  });
}

async function launchApp(appId) {
  const manifest = resolveManifest(appId);
  if (!manifest) {
    return {
      ok: false,
      manifestFound: false,
      message: `app not found: ${appId}`,
      host: "electron",
    };
  }
  const flatpak = await flatpakAvailable();
  if (!flatpak.ok) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      flatpakAvailable: false,
      host: "electron",
      message: "flatpak is not installed on this system.",
      actionableCommand: "install flatpak first, then retry /launch <app>",
      details: collectDetails(flatpak.result),
    };
  }
  const installed = await flatpakInstalled(manifest.flatpakId);
  if (!installed.installed) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      installed: false,
      flatpakAvailable: true,
      host: "electron",
      message: `${manifest.name} is not installed yet.`,
      actionableCommand: `/install ${manifest.id}`,
      details: [`launch command: ${manifest.launchCommand.join(" ")}`],
    };
  }
  logHosakaApps(`launching ${manifest.id}`, manifest.launchCommand);
  const [file, ...args] = manifest.launchCommand;
  const launched = fakeFlatpakEnabled()
    ? { ok: true, mocked: true }
    : await spawnDetached(file, args);
  if (!launched.ok) {
    return {
      ok: false,
      appId: manifest.id,
      manifestFound: true,
      installed: true,
      flatpakAvailable: true,
      host: "electron",
      message: `launch failed for ${manifest.name}.`,
      details: [`launch command: ${manifest.launchCommand.join(" ")}`, String(launched.error?.message || launched.error || "unknown error")],
    };
  }
  return {
    ok: true,
    appId: manifest.id,
    manifestFound: true,
    installed: true,
    flatpakAvailable: true,
    launched: true,
    host: "electron",
    message: `launched ${manifest.name}.`,
    details: [`launch command: ${manifest.launchCommand.join(" ")}`],
  };
}

ipcMain.handle("hosaka-apps:status", async (_event, appId) => getAppStatus(appId));
ipcMain.handle("hosaka-apps:install", async (_event, appId) => installApp(appId));
ipcMain.handle("hosaka-apps:launch", async (_event, appId) => launchApp(appId));

// Runtime listing — replaces the build-time Vite glob so newly-staged
// manifests appear without a frontend rebuild.
ipcMain.handle("hosaka-apps:list", async () => {
  return readAppManifests().map((m) => ({
    id: m.id,
    name: m.name,
    backend: m.backend,
    flatpak_id: m.flatpakId,
    install: { command: m.installCommand },
    launch: { command: m.launchCommand },
    aliases: m.aliases,
  }));
});

// Capability probe — lets the UI render an honest badge instead of
// blaming the user when flatpak just isn't there.
ipcMain.handle("hosaka-apps:capabilities", async () => {
  const fake = fakeFlatpakEnabled();
  const flatpak = await flatpakAvailable();
  return {
    host: "electron",
    platform: process.platform,
    flatpakAvailable: flatpak.ok,
    mocked: fake,
    note: fake
      ? "mock flatpak backend — installs/launches are simulated for dev."
      : flatpak.ok ? null : "flatpak is not installed on this host.",
  };
});

// Flathub catalog browser. We use the JSON API (no HTML scraping). Net
// requests go through Electron's `net` module so they inherit the kiosk
// session's proxy/cert config.
const FLATHUB_API = "https://flathub.org/api/v2";

function flathubFetchJson(url) {
  return new Promise((resolve, reject) => {
    const request = net.request({ method: "GET", url, redirect: "follow" });
    request.setHeader("Accept", "application/json");
    request.setHeader("User-Agent", "hosaka-kiosk/1.0 (+flathub-catalog)");
    let body = "";
    request.on("response", (response) => {
      response.on("data", (chunk) => { body += chunk.toString(); });
      response.on("end", () => {
        if (response.statusCode && response.statusCode >= 200 && response.statusCode < 300) {
          try { resolve(JSON.parse(body)); }
          catch (e) { reject(new Error(`flathub: bad json (${e.message})`)); }
        } else {
          reject(new Error(`flathub: http ${response.statusCode}`));
        }
      });
      response.on("error", reject);
    });
    request.on("error", reject);
    request.end();
  });
}

ipcMain.handle("hosaka-apps:flathub-search", async (_event, query) => {
  const q = String(query ?? "").trim();
  if (!q) return { ok: false, message: "empty query", hits: [] };
  try {
    const data = await flathubFetchJson(`${FLATHUB_API}/search/${encodeURIComponent(q)}`);
    const rows = Array.isArray(data?.hits) ? data.hits : Array.isArray(data) ? data : [];
    const hits = rows.slice(0, 25).map((row) => ({
      id: String(row.app_id ?? row.id ?? row.flatpakAppId ?? ""),
      name: String(row.name ?? row.app_name ?? row.title ?? ""),
      summary: String(row.summary ?? row.description ?? ""),
      icon: typeof row.icon === "string" ? row.icon : null,
      categories: Array.isArray(row.categories) ? row.categories.map(String) : [],
    })).filter((h) => h.id);
    return { ok: true, query: q, hits };
  } catch (error) {
    return { ok: false, message: String(error?.message ?? error), hits: [] };
  }
});

ipcMain.handle("hosaka-apps:flathub-meta", async (_event, flatpakId) => {
  const id = String(flatpakId ?? "").trim();
  if (!id) return { ok: false, message: "empty id" };
  try {
    const data = await flathubFetchJson(`${FLATHUB_API}/appstream/${encodeURIComponent(id)}`);
    return { ok: true, id, meta: data };
  } catch (error) {
    return { ok: false, id, message: String(error?.message ?? error) };
  }
});

// Stage a user-installable manifest. We deliberately write a real YAML
// file under hosaka-apps/apps/ so the existing install/launch path works
// unchanged AND the install is auditable / version-controllable.
ipcMain.handle("hosaka-apps:stage-manifest", async (_event, payload) => {
  const flatpakId = String(payload?.flatpak_id ?? "").trim();
  const name = String(payload?.name ?? flatpakId).trim();
  if (!flatpakId || !/^[A-Za-z0-9._-]+$/.test(flatpakId)) {
    return { ok: false, message: "invalid flatpak id" };
  }
  const id = normalizeAppToken(payload?.id || flatpakId.split(".").pop() || flatpakId);
  if (!id) return { ok: false, message: "invalid app id" };
  const filePath = path.join(APPS_DIR, `${id}.yaml`);
  if (fs.existsSync(filePath) && !payload?.overwrite) {
    return { ok: false, message: `manifest already staged: ${id}`, path: filePath };
  }
  const manifest = {
    id,
    name,
    category: String(payload?.category ?? "other"),
    description: String(payload?.description ?? `Flathub app ${flatpakId}.`),
    provider: String(payload?.provider ?? "Flathub"),
    backend: "flatpak",
    flatpak_id: flatpakId,
    install: { command: ["flatpak", "install", "-y", "--noninteractive", "flathub", flatpakId] },
    launch: { command: ["flatpak", "run", flatpakId] },
    aliases: Array.from(new Set([id, flatpakId.toLowerCase()])),
    memory: { profile: "unknown" },
    permissions_notes: ["Staged from Flathub catalog; review the app's own permissions before installing."],
    account_login_required: false,
    hosaka_manages_credentials: false,
    notes: ["User-staged via the app store panel."],
  };
  try {
    fs.mkdirSync(APPS_DIR, { recursive: true });
    fs.writeFileSync(filePath, YAML.stringify(manifest), "utf8");
    return { ok: true, id, path: filePath };
  } catch (error) {
    return { ok: false, message: String(error?.message ?? error) };
  }
});

function resolveStartUrl() {
  // 1. Explicit override always wins — systemd and the dev runner set this.
  if (process.env.HOSAKA_KIOSK_URL) return process.env.HOSAKA_KIOSK_URL;
  // 2. Prefer the local FastAPI. The SPA talks to /api/* and we need
  //    same-origin; serving the built bundle from file:// breaks that
  //    (Origin: null, cookies can't be set, etc.).
  //    We don't probe here because electron is launched by systemd AFTER
  //    hosaka-webserver.service is healthy; if it's not up we'll just
  //    show a "refused to connect" page and retry via Restart=always.
  if (!process.env.HOSAKA_KIOSK_NO_LOOPBACK) return "http://127.0.0.1:8421/";
  // 3. Opt-in file:// fallback for plain-laptop demos where no webserver
  //    is running. Broken /api/* is expected in that mode.
  const built = path.resolve(__dirname, "..", "hosaka", "web", "ui", "index.html");
  if (fs.existsSync(built)) return `file://${built}`;
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
  // Grant microphone and camera access so the SPA's getUserMedia calls work
  // inside the kiosk. Without this handler Electron silently denies all
  // permission requests (unlike a normal browser which prompts the user).
  session.defaultSession.setPermissionRequestHandler(
    (_webContents, permission, callback) => {
      const allowed = ["media", "microphone", "camera", "audioCapture", "videoCapture"];
      callback(allowed.includes(permission));
    },
  );

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
