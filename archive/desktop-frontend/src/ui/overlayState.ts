/**
 * overlayState — lightweight persisted state for floating instrument windows
 * that dispatch-open above the terminal.
 *
 * Keeps only the minimum needed to restore layout across reloads: whether the
 * surface is open, its last position/size, pinned flag, and a monotonic
 * focus timestamp for z-order. Actual media streams (mic/cam) live in the
 * components themselves so they can be torn down on unmount.
 */

export type OverlaySurfaceId = "mic_check" | "cam_check" | "spk_check" | "diag";

export type OverlayEntry = {
  id: OverlaySurfaceId;
  open: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  pinned: boolean;
  lastFocusedAt: number;
};

export type OverlaysDoc = {
  overlays: Partial<Record<OverlaySurfaceId, OverlayEntry>>;
};

export const INITIAL_OVERLAYS_DOC: OverlaysDoc = {
  overlays: {},
};

/** Default geometry per surface. Sized to feel like small diagnostic
 *  instruments, not web pages. Positions stagger so they don't overlap on
 *  first open. */
export const OVERLAY_DEFAULTS: Record<OverlaySurfaceId, { w: number; h: number; x: number; y: number; title: string; glyph: string }> = {
  mic_check: { w: 360, h: 240, x: 80, y: 90, title: "mic check", glyph: "🎙" },
  cam_check: { w: 360, h: 300, x: 120, y: 130, title: "cam check", glyph: "📷" },
  spk_check: { w: 360, h: 220, x: 160, y: 170, title: "spk check", glyph: "🔊" },
  diag: { w: 380, h: 260, x: 60, y: 60, title: "diagnostics", glyph: "⚇" },
};

export function makeOverlayEntry(
  id: OverlaySurfaceId,
  patch: Partial<OverlayEntry> = {},
): OverlayEntry {
  const def = OVERLAY_DEFAULTS[id];
  const now = Date.now();
  return {
    id,
    open: true,
    x: def.x,
    y: def.y,
    w: def.w,
    h: def.h,
    pinned: false,
    lastFocusedAt: now,
    ...patch,
  };
}

export const OVERLAY_OPEN_EVENT = "hosaka:overlay-open";
export const OVERLAY_CLOSE_EVENT = "hosaka:overlay-close";
export const OVERLAY_CLOSE_ALL_EVENT = "hosaka:overlay-close-all";
export const OVERLAY_FOCUS_EVENT = "hosaka:overlay-focus";

export type OverlayOpenDetail = { id: OverlaySurfaceId };
export type OverlayCloseDetail = { id: OverlaySurfaceId };
export type OverlayCloseAllDetail = { keepPinned?: boolean };
