const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

async function host({ lock = true } = {}) {
  const events = new Map();
  const signals = new Map();
  const windows = [];
  const messages = [];
  let quits = 0;
  let shortcut;
  let permission;
  class Window {
    constructor(options) {
      this.options = options;
      this.visible = false;
      this.url = "";
      this.events = new Map();
      this.webContents = {
        session: { clearCache: async () => {} },
        getURL: () => this.url,
        setWindowOpenHandler: callback => { this.popup = callback; },
        openDevTools: () => {},
      };
      windows.push(this);
    }
    isDestroyed() { return false; }
    isMinimized() { return false; }
    setAlwaysOnTop(value) { this.onTop = value; }
    show() { this.visible = true; }
    hide() { this.visible = false; }
    focus() { this.focused = true; }
    on(name, callback) { this.events.set(name, callback); }
    once(name, callback) { this.events.set(name, callback); }
    async loadURL(url) { this.url = url; }
  }
  const electron = {
    app: {
      commandLine: { appendSwitch: () => {} },
      disableHardwareAcceleration: () => {},
      requestSingleInstanceLock: () => lock,
      quit: () => { quits++; },
      on: (name, callback) => events.set(name, callback),
      whenReady: async () => {},
    },
    BrowserWindow: Window,
    globalShortcut: {
      register: (_key, callback) => { shortcut = callback; return true; },
      unregisterAll: () => {},
    },
    session: { defaultSession: { setPermissionRequestHandler: callback => { permission = callback; } } },
  };
  const fakeFs = {
    mkdirSync: () => {},
    writeFileSync: () => {},
    existsSync: () => false,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../main.js"), "utf8"), {
    require: name => name === "electron" ? electron : name === "node:fs" ? fakeFs : require(name),
    process: { pid: 123, platform: "linux", env: {}, on: (name, callback) => signals.set(name, callback) },
    URL,
    console: { warn: (...args) => messages.push(args), error: (...args) => messages.push(args) },
  });
  await new Promise(resolve => setImmediate(resolve));
  return { events, signals, windows, messages, shortcut, permission, quits };
}

test("terminal host has no desktop bridges and does not cover RetroArch", async () => {
  const kiosk = await host();
  assert.equal(kiosk.windows.length, 1);
  const win = kiosk.windows[0];
  assert.equal(win.url, "http://127.0.0.1:8421/");
  assert.equal(win.options.alwaysOnTop, false);
  assert.equal(win.options.webPreferences.webviewTag, undefined);
  assert.equal(win.options.webPreferences.preload, undefined);
  assert.equal(win.options.webPreferences.nodeIntegration, false);
  assert.equal(win.popup().action, "deny");
  let allowed;
  kiosk.permission(null, "media", value => { allowed = value; });
  assert.equal(allowed, false);
});

test("signals and Super+H preserve the same window", async () => {
  const kiosk = await host();
  const win = kiosk.windows[0];
  kiosk.signals.get("SIGUSR1")();
  assert.equal(win.visible, false);
  kiosk.signals.get("SIGUSR2")();
  assert.equal(win.visible, true);
  assert.equal(win.onTop, false);
  kiosk.shortcut();
  assert.equal(win.focused, true);
  assert.equal(kiosk.windows.length, 1);
});

test("second instance retargets instead of opening a duplicate", async () => {
  const kiosk = await host();
  kiosk.events.get("second-instance")(null, [], "", { hosakaKioskUrl: "http://localhost:5173/" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(kiosk.windows.length, 1);
  assert.equal(kiosk.windows[0].url, "http://localhost:5173/");
});

test("failed singleton lock quits without creating a window", async () => {
  const kiosk = await host({ lock: false });
  assert.equal(kiosk.quits, 1);
  assert.equal(kiosk.windows.length, 0);
});
