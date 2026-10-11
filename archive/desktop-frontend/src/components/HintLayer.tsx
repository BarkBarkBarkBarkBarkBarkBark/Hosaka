/**
 * HintLayer — Vimium-style click-anything-with-the-keyboard overlay.
 *
 * Toggles on a `hosaka:hint-toggle` event (fired by Ctrl+; via useShortcuts).
 * When active, it scans the document for buttons / tabs / links / inputs /
 * elements with [data-hint], assigns each a 1–2 letter badge, and listens
 * for keystrokes. Typing the badge focuses or clicks the target.
 *
 * Esc cancels. Backspace deletes the last typed letter.
 */
import { useEffect, useMemo, useState } from "react";
import { HINT_TOGGLE_EVENT } from "../ui/useShortcuts";

const SELECTOR = [
  "[data-hint]",
  "button:not([disabled])",
  "[role='button']",
  "[role='tab']",
  "[role='menuitem']",
  "a[href]",
  "select",
  "input:not([type='hidden']):not([disabled])",
  "textarea:not([disabled])",
].join(", ");

const ALPHA = "ASDFGHJKLQWERTYUIOPZXCVBNM";

function makeBadges(n: number): string[] {
  if (n <= ALPHA.length) return Array.from({ length: n }, (_, i) => ALPHA[i]);
  const out: string[] = [];
  for (let i = 0; i < ALPHA.length && out.length < n; i++) {
    for (let j = 0; j < ALPHA.length && out.length < n; j++) {
      out.push(ALPHA[i] + ALPHA[j]);
    }
  }
  return out;
}

type Hint = { el: HTMLElement; badge: string; rect: DOMRect };

function isVisible(el: HTMLElement): boolean {
  if (!el.isConnected) return false;
  const rect = el.getBoundingClientRect();
  if (rect.width < 6 || rect.height < 6) return false;
  if (rect.bottom < 0 || rect.top > window.innerHeight) return false;
  if (rect.right < 0 || rect.left > window.innerWidth) return false;
  const cs = getComputedStyle(el);
  if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") return false;
  return true;
}

export function HintLayer() {
  const [active, setActive] = useState(false);
  const [typed, setTyped] = useState("");
  const [hints, setHints] = useState<Hint[]>([]);

  useEffect(() => {
    const onToggle = () => setActive((v) => !v);
    window.addEventListener(HINT_TOGGLE_EVENT, onToggle);
    return () => window.removeEventListener(HINT_TOGGLE_EVENT, onToggle);
  }, []);

  useEffect(() => {
    if (!active) { setHints([]); setTyped(""); return; }
    const all = Array.from(document.querySelectorAll<HTMLElement>(SELECTOR));
    const visible = all.filter(isVisible);
    const badges = makeBadges(visible.length);
    setHints(visible.map((el, i) => ({ el, badge: badges[i], rect: el.getBoundingClientRect() })));
    setTyped("");
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault(); e.stopPropagation();
        setActive(false);
        return;
      }
      if (e.key === "Backspace") {
        e.preventDefault(); e.stopPropagation();
        setTyped((p) => p.slice(0, -1));
        return;
      }
      if (e.key.length !== 1) return;
      const ch = e.key.toUpperCase();
      if (!/[A-Z]/.test(ch)) return;
      e.preventDefault(); e.stopPropagation();
      const next = typed + ch;
      const exact = hints.find((h) => h.badge === next);
      if (exact) {
        try {
          if (exact.el instanceof HTMLInputElement || exact.el instanceof HTMLTextAreaElement || exact.el instanceof HTMLSelectElement) {
            exact.el.focus();
          } else {
            exact.el.click();
          }
        } catch { /* ignore */ }
        setActive(false);
        return;
      }
      const remaining = hints.filter((h) => h.badge.startsWith(next));
      if (remaining.length === 0) {
        setActive(false);
        return;
      }
      setTyped(next);
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true } as EventListenerOptions);
  }, [active, hints, typed]);

  const visibleHints = useMemo(
    () => hints.filter((h) => h.badge.startsWith(typed)),
    [hints, typed],
  );

  if (!active) return null;
  return (
    <div className="hint-layer" aria-hidden>
      {visibleHints.map((h) => (
        <span
          key={h.badge}
          className="hint-badge"
          style={{ left: h.rect.left + window.scrollX, top: h.rect.top + window.scrollY }}
        >
          <span className="hint-typed">{typed}</span>
          <span className="hint-rest">{h.badge.slice(typed.length)}</span>
        </span>
      ))}
    </div>
  );
}
