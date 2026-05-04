/**
 * OverlayStack — renders all open instrument overlays at the shell root.
 *
 * Listens for hosaka:overlay-open / hosaka:overlay-close / hosaka:overlay-focus
 * / hosaka:overlay-close-all events. Child overlay components are React.lazy
 * so their media code (mic/cam) only ships when someone actually opens them.
 *
 * Uses the synced "overlays" doc so layout + pinned flags persist across
 * reloads. Closed overlays are unmounted (not hidden) so streams stop.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo } from "react";
import { useSyncedDoc } from "../sync/useSyncedDoc";
import { SurfaceWindow } from "./SurfaceWindow";
import {
  INITIAL_OVERLAYS_DOC,
  OVERLAY_CLOSE_ALL_EVENT,
  OVERLAY_CLOSE_EVENT,
  OVERLAY_DEFAULTS,
  OVERLAY_FOCUS_EVENT,
  OVERLAY_OPEN_EVENT,
  makeOverlayEntry,
  type OverlayCloseAllDetail,
  type OverlayCloseDetail,
  type OverlayOpenDetail,
  type OverlaySurfaceId,
  type OverlaysDoc,
} from "../ui/overlayState";

const MicCheckWindow = lazy(() =>
  import("../panels/overlays/MicCheckWindow").then((m) => ({ default: m.MicCheckWindow })),
);
const CamCheckWindow = lazy(() =>
  import("../panels/overlays/CamCheckWindow").then((m) => ({ default: m.CamCheckWindow })),
);
const SpkCheckWindow = lazy(() =>
  import("../panels/overlays/SpkCheckWindow").then((m) => ({ default: m.SpkCheckWindow })),
);
const DiagOverlay = lazy(() =>
  import("../panels/overlays/DiagOverlay").then((m) => ({ default: m.DiagOverlay })),
);

function renderOverlayChild(id: OverlaySurfaceId, onClose: () => void) {
  switch (id) {
    case "mic_check":
      return <MicCheckWindow onClose={onClose} />;
    case "cam_check":
      return <CamCheckWindow onClose={onClose} />;
    case "spk_check":
      return <SpkCheckWindow onClose={onClose} />;
    case "diag":
      return <DiagOverlay onClose={onClose} />;
  }
}

export function OverlayStack() {
  const [doc, update] = useSyncedDoc<OverlaysDoc>("overlays", INITIAL_OVERLAYS_DOC);

  const openOverlay = useCallback((id: OverlaySurfaceId) => {
    update((d) => {
      if (!d.overlays || typeof d.overlays !== "object") d.overlays = {};
      const existing = d.overlays[id];
      if (existing) {
        existing.open = true;
        existing.lastFocusedAt = Date.now();
      } else {
        d.overlays[id] = makeOverlayEntry(id);
      }
    });
  }, [update]);

  const closeOverlay = useCallback((id: OverlaySurfaceId) => {
    update((d) => {
      const existing = d.overlays?.[id];
      if (existing) existing.open = false;
    });
  }, [update]);

  const focusOverlay = useCallback((id: OverlaySurfaceId) => {
    update((d) => {
      const existing = d.overlays?.[id];
      if (existing) existing.lastFocusedAt = Date.now();
    });
  }, [update]);

  const moveOverlay = useCallback((id: OverlaySurfaceId, x: number, y: number) => {
    update((d) => {
      const existing = d.overlays?.[id];
      if (existing) {
        existing.x = x;
        existing.y = y;
      }
    });
  }, [update]);

  const togglePin = useCallback((id: OverlaySurfaceId) => {
    update((d) => {
      const existing = d.overlays?.[id];
      if (existing) existing.pinned = !existing.pinned;
    });
  }, [update]);

  const closeAll = useCallback((keepPinned: boolean) => {
    update((d) => {
      const overlays = d.overlays ?? {};
      for (const key of Object.keys(overlays) as OverlaySurfaceId[]) {
        const entry = overlays[key];
        if (!entry) continue;
        if (keepPinned && entry.pinned) continue;
        entry.open = false;
      }
    });
  }, [update]);

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<OverlayOpenDetail>).detail;
      if (detail?.id) openOverlay(detail.id);
    };
    const onClose = (event: Event) => {
      const detail = (event as CustomEvent<OverlayCloseDetail>).detail;
      if (detail?.id) closeOverlay(detail.id);
    };
    const onFocus = (event: Event) => {
      const detail = (event as CustomEvent<OverlayOpenDetail>).detail;
      if (detail?.id) focusOverlay(detail.id);
    };
    const onCloseAll = (event: Event) => {
      const detail = (event as CustomEvent<OverlayCloseAllDetail>).detail;
      closeAll(Boolean(detail?.keepPinned));
    };
    window.addEventListener(OVERLAY_OPEN_EVENT, onOpen as EventListener);
    window.addEventListener(OVERLAY_CLOSE_EVENT, onClose as EventListener);
    window.addEventListener(OVERLAY_FOCUS_EVENT, onFocus as EventListener);
    window.addEventListener(OVERLAY_CLOSE_ALL_EVENT, onCloseAll as EventListener);
    return () => {
      window.removeEventListener(OVERLAY_OPEN_EVENT, onOpen as EventListener);
      window.removeEventListener(OVERLAY_CLOSE_EVENT, onClose as EventListener);
      window.removeEventListener(OVERLAY_FOCUS_EVENT, onFocus as EventListener);
      window.removeEventListener(OVERLAY_CLOSE_ALL_EVENT, onCloseAll as EventListener);
    };
  }, [openOverlay, closeOverlay, focusOverlay, closeAll]);

  const openEntries = useMemo(() => {
    const entries = Object.values(doc.overlays ?? {}).filter(
      (e): e is NonNullable<typeof e> => Boolean(e && e.open),
    );
    entries.sort((a, b) => a.lastFocusedAt - b.lastFocusedAt);
    return entries;
  }, [doc.overlays]);

  // #region agent log
  useEffect(() => {
    const dbg = (window as unknown as { __hosakaDbg?: (loc: string, msg: string, data?: Record<string, unknown>) => void }).__hosakaDbg;
    dbg?.("OverlayStack.tsx:state", "overlay state", {
      docOverlays: doc.overlays,
      openCount: openEntries.length,
      openIds: openEntries.map((e) => e.id),
    });
  }, [doc.overlays, openEntries]);
  // #endregion

  if (openEntries.length === 0) return null;

  return (
    <div className="overlay-stack" aria-live="polite">
      {openEntries.map((entry, idx) => {
        const def = OVERLAY_DEFAULTS[entry.id];
        return (
          <Suspense key={entry.id} fallback={null}>
            <SurfaceWindow
              title={def.title}
              glyph={def.glyph}
              x={entry.x}
              y={entry.y}
              w={entry.w}
              h={entry.h}
              pinned={entry.pinned}
              zIndex={80 + idx}
              onClose={() => closeOverlay(entry.id)}
              onTogglePin={() => togglePin(entry.id)}
              onMove={(x, y) => moveOverlay(entry.id, x, y)}
              onFocus={() => focusOverlay(entry.id)}
            >
              {renderOverlayChild(entry.id, () => closeOverlay(entry.id))}
            </SurfaceWindow>
          </Suspense>
        );
      })}
    </div>
  );
}
