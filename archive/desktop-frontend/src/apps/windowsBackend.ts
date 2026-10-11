/**
 * windowsBackend — thin client for /api/v1/windows.
 *
 * The webserver shells out to xdotool against the kiosk seat's DISPLAY/
 * XAUTHORITY (see _resolve_kiosk_seat_env in api_v1.py). We never touch
 * X11 from the renderer.
 *
 * Used by the WindowDock to render a slim task strip for OS-level
 * windows (foliate, spotify, etc.) so the operator can raise/minimize/
 * close them without leaving the kiosk SPA.
 */

export type HosakaWindow = {
  /** xdotool window id, decimal string (e.g. "20971524"). */
  wid: string;
  title: string;
  wmClass: string;
  pid: number;
  /** Hosaka manifest id if the window's WM_CLASS matched a known app. */
  appId: string | null;
};

export type WindowsListResponse = {
  ok: boolean;
  windows: HosakaWindow[];
  count: number;
  note?: string | null;
};

const BASE = "/api/v1/windows";

async function jsonOrNull<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(path, { credentials: "same-origin", ...init });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function listWindows(): Promise<WindowsListResponse> {
  const got = await jsonOrNull<WindowsListResponse>(BASE);
  return got ?? { ok: false, windows: [], count: 0, note: "request failed" };
}

export type WindowAction = "raise" | "minimize" | "close";

export async function actOnWindow(wid: string, action: WindowAction): Promise<{ ok: boolean; message?: string }> {
  const got = await jsonOrNull<{ ok: boolean; message?: string }>(
    `${BASE}/${encodeURIComponent(wid)}/${encodeURIComponent(action)}`,
    { method: "POST" },
  );
  return got ?? { ok: false, message: "request failed" };
}

/** Event name dispatched on `window` after a successful flatpak launch
 *  so the dock can refresh on demand instead of polling tightly. */
export const APP_LAUNCHED_EVENT = "hosaka:app-launched";
