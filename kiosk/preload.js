/**
 * Hosaka kiosk — preload script.
 *
 * Runs in a context-isolated world before the SPA loads, and exposes a
 * single bridge object the frontend's browserAdapter looks for. When this
 * bridge is present, the WebPanel picks the "native-webview" render path
 * instead of the plain iframe fallback.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hosakaBrowserAdapter", {
  mode: "native-webview",

  // The <webview> tag mounts inline inside the WebPanel, so there's no
  // host-managed surface to launch. We still expose the function so the
  // adapter's feature detection reports the right mode.
  launchNativeWebview: async () => true,
});

contextBridge.exposeInMainWorld("hosakaAppHost", {
  getStatus: async (appId) => ipcRenderer.invoke("hosaka-apps:status", appId),
  installApp: async (appId) => ipcRenderer.invoke("hosaka-apps:install", appId),
  launchApp: async (appId) => ipcRenderer.invoke("hosaka-apps:launch", appId),
  listManifests: async () => ipcRenderer.invoke("hosaka-apps:list"),
  capabilities: async () => ipcRenderer.invoke("hosaka-apps:capabilities"),
  flathubSearch: async (query) => ipcRenderer.invoke("hosaka-apps:flathub-search", query),
  flathubMeta: async (flatpakId) => ipcRenderer.invoke("hosaka-apps:flathub-meta", flatpakId),
  stageManifest: async (payload) => ipcRenderer.invoke("hosaka-apps:stage-manifest", payload),
});
