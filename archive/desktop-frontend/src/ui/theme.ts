/**
 * Theme + orb customization registry.
 *
 * Themes are CSS classes on <html> (`theme-amber`, `theme-pink`, etc.)
 * that swap the accent palette via `:root.theme-*` overrides in app.css.
 *
 * Orb customization is a layer on top: a chosen color (CSS color value)
 * and an "orbit text" string. Both override the theme's defaults via
 * inline style on the FloatingOrb element + a custom event bus so the
 * terminal can flip them live with `/orb color` and `/orb orbit`.
 */

export type ThemeId =
  | "amber"      // signature gold/black (default)
  | "pink"       // pink + cream, soft daylight
  | "rainbow"    // chromatic — animated hue rotation on accents
  | "amber-mono" // amber text on pure black, hacker terminal vibes
  | "matrix";    // green text + matrix backdrop

export const THEMES: { id: ThemeId; label: string; hint: string }[] = [
  { id: "amber",      label: "amber",      hint: "signature gold on black" },
  { id: "pink",       label: "pink",       hint: "soft pink on cream" },
  { id: "rainbow",    label: "rainbow",    hint: "chromatic, hue-rotating" },
  { id: "amber-mono", label: "amber mono", hint: "amber text on pure black" },
  { id: "matrix",     label: "matrix",     hint: "green text, falling code" },
];

const THEME_KEY = "hosaka.theme";
const ORB_COLOR_KEY = "hosaka.orb.color";
const ORB_ORBIT_KEY = "hosaka.orb.orbit";

export function getStoredTheme(): ThemeId {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v && THEMES.some((t) => t.id === v)) return v as ThemeId;
  } catch { /* ignore */ }
  return "amber";
}

export function applyTheme(id: ThemeId): void {
  const root = document.documentElement;
  for (const t of THEMES) root.classList.remove(`theme-${t.id}`);
  root.classList.add(`theme-${id}`);
  try { localStorage.setItem(THEME_KEY, id); } catch { /* ignore */ }
  // Notify imperative consumers (xterm, canvas, etc.) that CSS vars changed.
  try {
    window.dispatchEvent(new CustomEvent("hosaka:theme-changed", { detail: id }));
  } catch { /* SSR */ }
}

export function getStoredOrbColor(): string | null {
  try { return localStorage.getItem(ORB_COLOR_KEY); } catch { return null; }
}

export function setOrbColor(color: string | null): void {
  try {
    if (color) localStorage.setItem(ORB_COLOR_KEY, color);
    else localStorage.removeItem(ORB_COLOR_KEY);
  } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent("hosaka:orb-customize", {
    detail: { color: color ?? undefined },
  }));
}

export function getStoredOrbOrbit(): string | null {
  try { return localStorage.getItem(ORB_ORBIT_KEY); } catch { return null; }
}

export function setOrbOrbit(text: string | null): void {
  try {
    if (text) localStorage.setItem(ORB_ORBIT_KEY, text);
    else localStorage.removeItem(ORB_ORBIT_KEY);
  } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent("hosaka:orb-customize", {
    detail: { orbit: text ?? undefined },
  }));
}

/** Boot-time: apply persisted theme before React mounts to avoid flash. */
export function bootTheme(): void {
  applyTheme(getStoredTheme());
}
