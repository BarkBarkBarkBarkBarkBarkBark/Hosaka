/**
 * WindowDock — slim strip showing real X11 windows on the kiosk seat.
 *
 * "open apps" in HosakaMenu only knows about Hosaka tabs. Foliate /
 * Spotify / etc. spawn outside the SPA, so we ask the webserver to
 * enumerate them via xdotool (see /api/v1/windows) and render a tiny
 * dock so the operator can raise / minimize / close without leaving
 * the kiosk.
 *
 * Cadence: one poll on mount, then every 60s, plus an on-demand poll
 * whenever flatpakBackend dispatches `hosaka:app-launched`. We never
 * tight-poll — the kiosk's CPU budget is too small.
 *
 * The dock renders nothing when there are no external windows, so it
 * stays out of the way until something is actually open.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  APP_LAUNCHED_EVENT,
  actOnWindow,
  listWindows,
  type HosakaWindow,
} from "../apps/windowsBackend";
import { getAppDefinition, type AppId } from "../ui/appRegistry";

const POLL_MS = 60_000;

function glyphFor(win: HosakaWindow): string {
  if (win.appId) {
    const def = getAppDefinition(win.appId as AppId);
    if (def?.glyph) return def.glyph;
  }
  const seed = (win.title || win.wmClass || "?").trim();
  return seed ? seed.charAt(0).toUpperCase() : "?";
}

function labelFor(win: HosakaWindow): string {
  if (win.appId) {
    const def = getAppDefinition(win.appId as AppId);
    if (def?.title) return def.title;
  }
  return win.title || win.wmClass || `win ${win.wid}`;
}

export function WindowDock(): JSX.Element | null {
  const [windows, setWindows] = useState<HosakaWindow[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const inflight = useRef(false);

  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const res = await listWindows();
      if (res.ok) setWindows(res.windows);
    } finally {
      inflight.current = false;
    }
  }, []);

  useEffect(() => {
    refresh();
    const iv = window.setInterval(refresh, POLL_MS);
    const onLaunch = () => {
      // give the app a moment to map a window before we ask
      window.setTimeout(refresh, 1500);
      window.setTimeout(refresh, 5000);
    };
    window.addEventListener(APP_LAUNCHED_EVENT, onLaunch);
    return () => {
      window.clearInterval(iv);
      window.removeEventListener(APP_LAUNCHED_EVENT, onLaunch);
    };
  }, [refresh]);

  const act = useCallback(
    async (win: HosakaWindow, action: "raise" | "minimize" | "close") => {
      const key = `${win.wid}:${action}`;
      setBusy(key);
      try {
        await actOnWindow(win.wid, action);
      } finally {
        setBusy(null);
        // close shrinks the list; raise/minimize don't, but a refresh is cheap
        window.setTimeout(refresh, 400);
      }
    },
    [refresh],
  );

  if (windows.length === 0) return null;

  return (
    <div className="hosaka-windowdock" role="toolbar" aria-label="open desktop windows">
      {windows.map((win) => {
        const label = labelFor(win);
        const isClosing = busy === `${win.wid}:close`;
        return (
          <div
            key={win.wid}
            className="hosaka-windowdock-item"
            data-app-id={win.appId ?? undefined}
          >
            <button
              type="button"
              className="hosaka-windowdock-btn hosaka-windowdock-raise"
              onClick={() => act(win, "raise")}
              title={`raise · ${label}`}
              disabled={isClosing}
            >
              <span className="hosaka-windowdock-glyph" aria-hidden="true">{glyphFor(win)}</span>
              <span className="hosaka-windowdock-label">{label}</span>
            </button>
            <button
              type="button"
              className="hosaka-windowdock-btn hosaka-windowdock-min"
              onClick={() => act(win, "minimize")}
              title="minimize"
              disabled={isClosing}
              aria-label={`minimize ${label}`}
            >_</button>
            <button
              type="button"
              className="hosaka-windowdock-btn hosaka-windowdock-close"
              onClick={() => act(win, "close")}
              title="close"
              disabled={isClosing}
              aria-label={`close ${label}`}
            >×</button>
          </div>
        );
      })}
    </div>
  );
}

export default WindowDock;
