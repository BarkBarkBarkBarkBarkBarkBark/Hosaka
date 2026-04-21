/**
 * Hosaka kiosk — preload script.
 *
 * Runs in a context-isolated world before the SPA loads, and exposes a
 * single bridge object the frontend's browserAdapter looks for. When this
 * bridge is present, the WebPanel picks the "native-webview" render path
 * instead of the plain iframe fallback.
 */
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("hosakaBrowserAdapter", {
  mode: "native-webview",

  // The <webview> tag mounts inline inside the WebPanel, so there's no
  // host-managed surface to launch. We still expose the function so the
  // adapter's feature detection reports the right mode.
  launchNativeWebview: async () => true,
});
