/**
 * shortcuts — single source of truth for keyboard chords and slash commands.
 *
 * Both the global keydown listener (useShortcuts) and the in-terminal `/help`
 * / `/commands` printer derive from the SHORTCUTS registry, so a chord and a
 * command stay describable in one place.
 *
 * A "chord" is a normalized string like "Ctrl+T", "Ctrl+Shift+/", "Escape",
 * or "?". Comparison is case-insensitive on the key letter.
 *
 * `scope` distinguishes built-in canon shortcuts from user-defined ones; user
 * bindings are layered on top via loadUserShortcuts() (localStorage).
 */
import type { HosakaUiCommand } from "./hosakaUi";

export type ShortcutScope = "canon" | "user";

export type ShortcutDef = {
  id: string;
  chord: string;            // normalized, e.g. "Ctrl+T"
  label: string;            // short human description
  command: HosakaUiCommand; // what to dispatch
  scope: ShortcutScope;
  // when true, fire even if focus is on an <input>/<textarea>. default false.
  whenTyping?: boolean;
};

export const CANON_SHORTCUTS: ShortcutDef[] = [
  { id: "focus.terminal", chord: "Ctrl+T", label: "focus terminal",
    command: { id: "ui.focus_terminal" }, scope: "canon" },
  { id: "open.orb", chord: "Ctrl+O", label: "open voice orb",
    command: { id: "ui.toggle_orb" }, scope: "canon" },
  { id: "toggle.menu", chord: "Ctrl+M", label: "toggle menu",
    command: { id: "ui.toggle_menu" }, scope: "canon" },
  { id: "toggle.chrome", chord: "Ctrl+B", label: "collapse / expand chrome",
    command: { id: "ui.toggle_chrome" }, scope: "canon" },
  { id: "open.help", chord: "Ctrl+/", label: "show shortcuts + commands",
    command: { id: "ui.open_panel", target: "help" }, scope: "canon" },
  { id: "open.help.alt", chord: "?", label: "show shortcuts + commands",
    command: { id: "ui.open_panel", target: "help" }, scope: "canon" },
  { id: "open.devices", chord: "Ctrl+D", label: "open devices",
    command: { id: "ui.open_panel", target: "diagnostics" }, scope: "canon" },
  { id: "open.docs", chord: "Ctrl+E", label: "open documents",
    command: { id: "ui.open_panel", target: "docs" }, scope: "canon" },
  { id: "open.web", chord: "Ctrl+L", label: "open web",
    command: { id: "ui.open_panel", target: "web" }, scope: "canon" },
  { id: "open.games", chord: "Ctrl+G", label: "open games",
    command: { id: "ui.open_panel", target: "games" }, scope: "canon" },
  { id: "hint.start", chord: "Ctrl+;", label: "label every clickable element",
    command: { id: "ui.open_panel", target: "__hint__" }, scope: "canon" },
];

const USER_KEY = "hosaka.user-shortcuts";

export function loadUserShortcuts(): ShortcutDef[] {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(USER_KEY) : null;
    if (!raw) return [];
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr.filter((s): s is ShortcutDef =>
      s && typeof s.chord === "string" && typeof s.id === "string" && s.command,
    );
  } catch { return []; }
}

export function saveUserShortcuts(shortcuts: ShortcutDef[]): void {
  try { localStorage.setItem(USER_KEY, JSON.stringify(shortcuts)); } catch { /* quota */ }
}

export function getAllShortcuts(): ShortcutDef[] {
  return [...CANON_SHORTCUTS, ...loadUserShortcuts()];
}

/**
 * Build a normalized chord string from a KeyboardEvent.
 *
 * Order is fixed: Ctrl+Alt+Shift+Meta+<Key>. Letter keys are upper-cased so
 * "Ctrl+t" and "Ctrl+T" compare equal. Bare keys like "Escape" or "?" come
 * through as just the key name.
 */
export function chordFromEvent(e: KeyboardEvent): string {
  const parts: string[] = [];
  if (e.ctrlKey) parts.push("Ctrl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey && e.key.length !== 1) parts.push("Shift");
  if (e.metaKey) parts.push("Meta");
  let key = e.key;
  if (key === " ") key = "Space";
  if (key.length === 1) key = key.toUpperCase();
  parts.push(key);
  return parts.join("+");
}

export function chordsEqual(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

/** True when the chord matches a registered shortcut. Used by xterm bypass. */
export function isRegisteredChord(chord: string): boolean {
  return getAllShortcuts().some((s) => chordsEqual(s.chord, chord));
}

/** Find a shortcut for a given event, honoring whenTyping rules. */
export function matchShortcut(e: KeyboardEvent, isTyping: boolean): ShortcutDef | null {
  const chord = chordFromEvent(e);
  for (const s of getAllShortcuts()) {
    if (!chordsEqual(s.chord, chord)) continue;
    if (isTyping && !s.whenTyping) continue;
    return s;
  }
  return null;
}
