/**
 * SurfaceWindow — small 90s-instrument-style floating window.
 *
 * Renders a title bar with glyph + label, pin/close buttons, and a body.
 * Drag by the title bar only (pointer events, no lib). Position and size
 * are controlled props so the parent can persist them in overlayState.
 *
 * Intentionally dumb about media: children own getUserMedia lifecycles and
 * will stop streams when they unmount, so closing the window should always
 * release the mic/cam.
 */
import {
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export type SurfaceWindowProps = {
  title: string;
  glyph?: string;
  x: number;
  y: number;
  w: number;
  h: number;
  pinned?: boolean;
  zIndex?: number;
  onClose: () => void;
  onTogglePin?: () => void;
  onMove?: (x: number, y: number) => void;
  onFocus?: () => void;
  children: ReactNode;
};

function clampToViewport(x: number, y: number, w: number, _h: number): { x: number; y: number } {
  if (typeof window === "undefined") return { x, y };
  const maxX = Math.max(0, window.innerWidth - Math.min(w, 120));
  const maxY = Math.max(0, window.innerHeight - 40);
  return {
    x: Math.min(Math.max(0, x), maxX),
    y: Math.min(Math.max(0, y), maxY),
  };
}

export function SurfaceWindow({
  title,
  glyph,
  x,
  y,
  w,
  h,
  pinned,
  zIndex,
  onClose,
  onTogglePin,
  onMove,
  onFocus,
  children,
}: SurfaceWindowProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ dx: number; dy: number } | null>(null);
  const [pos, setPos] = useState({ x, y });

  useEffect(() => {
    setPos({ x, y });
  }, [x, y]);

  const handlePointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("[data-surface-noclick='true']")) return;
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    setDrag({ dx: event.clientX - rect.left, dy: event.clientY - rect.top });
    onFocus?.();
    try { (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId); } catch { /* noop */ }
  }, [onFocus]);

  useEffect(() => {
    if (!drag) return;
    const onMoveEvt = (event: PointerEvent) => {
      const next = clampToViewport(event.clientX - drag.dx, event.clientY - drag.dy, w, h);
      setPos(next);
    };
    const onUp = () => {
      setDrag(null);
      onMove?.(pos.x, pos.y);
    };
    window.addEventListener("pointermove", onMoveEvt);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMoveEvt);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [drag, h, w, onMove, pos.x, pos.y]);

  return (
    <div
      ref={ref}
      className={`surface-window${pinned ? " surface-window--pinned" : ""}`}
      style={{ left: pos.x, top: pos.y, width: w, minHeight: h, zIndex: zIndex ?? 80 }}
      role="dialog"
      aria-label={title}
      onMouseDown={() => onFocus?.()}
    >
      <div
        className="surface-window-titlebar"
        onPointerDown={handlePointerDown}
      >
        <span className="surface-window-glyph">{glyph ?? "▣"}</span>
        <span className="surface-window-title">{title}</span>
        <span className="surface-window-spacer" />
        {onTogglePin && (
          <button
            type="button"
            className={`surface-window-btn ${pinned ? "is-on" : ""}`}
            aria-label={pinned ? "unpin" : "pin"}
            title={pinned ? "unpin" : "pin"}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={onTogglePin}
          >◉</button>
        )}
        <button
          type="button"
          className="surface-window-btn surface-window-close"
          aria-label="close"
          title="close"
          onPointerDown={(e) => { e.stopPropagation(); onClose(); }}
        >✕</button>
      </div>
      <div className="surface-window-body">
        {children}
      </div>
    </div>
  );
}
