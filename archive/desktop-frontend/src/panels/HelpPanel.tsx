/**
 * HelpPanel — keyboard shortcut + slash-command reference.
 *
 * Lists every chord registered in CANON_SHORTCUTS plus any user shortcuts,
 * grouped by scope. Also surfaces the static slash-command catalog so the
 * operator can discover both modalities from one tab.
 *
 * No mouse required: the page is a flat scrollable list focused via the
 * shortcut Ctrl+/ that opened it. Esc closes the tab via the global key
 * handler in App.tsx.
 */
import { useMemo } from "react";
import { CANON_SHORTCUTS, loadUserShortcuts, type ShortcutDef } from "../ui/shortcuts";

function Row({ s }: { s: ShortcutDef }) {
  return (
    <li className="help-row">
      <kbd className="help-chord">{s.chord}</kbd>
      <span className="help-label">{s.label}</span>
      <span className="help-cmd dim">{commandSummary(s)}</span>
    </li>
  );
}

function commandSummary(s: ShortcutDef): string {
  const c = s.command;
  switch (c.id) {
    case "ui.open_panel": return `open ${c.target}`;
    case "ui.focus_terminal": return "focus terminal";
    case "ui.toggle_orb": return "voice orb";
    case "ui.toggle_menu": return "menu";
    case "ui.toggle_chrome": return "chrome";
    case "ui.show_diagnostics": return "diagnostics";
    default: return c.id;
  }
}

const CANON_SLASH: Array<{ name: string; desc: string }> = [
  { name: "/help", desc: "in-terminal help screen" },
  { name: "/commands", desc: "list every slash command" },
  { name: "/terminal", desc: "focus the full terminal" },
  { name: "/orb", desc: "open the voice orb" },
  { name: "/menu", desc: "toggle the side menu" },
  { name: "/device", desc: "open devices overlay" },
  { name: "/device check mic|cam|spk", desc: "open a device check tab" },
  { name: "/devices open", desc: "open the full devices panel" },
  { name: "/games", desc: "open games" },
  { name: "/web <url>", desc: "open the web panel at url" },
  { name: "/launch <app>", desc: "open any registered app" },
  { name: "/messages, /inbox, /docs, /reading, /todo", desc: "open the named app" },
];

export function HelpPanel() {
  const user = useMemo(() => loadUserShortcuts(), []);
  return (
    <div className="help-panel">
      <header className="panel-header">
        <h2><span className="panel-glyph">?</span> shortcuts &amp; commands</h2>
        <p className="panel-sub">keyboard above all — every action has a chord and / or a slash command.</p>
      </header>
      <section className="help-section">
        <h3>chords · canon</h3>
        <ul className="help-list">
          {CANON_SHORTCUTS.map((s) => <Row key={s.id} s={s} />)}
        </ul>
      </section>
      {user.length > 0 && (
        <section className="help-section">
          <h3>chords · user</h3>
          <ul className="help-list">
            {user.map((s) => <Row key={s.id} s={s} />)}
          </ul>
        </section>
      )}
      <section className="help-section">
        <h3>slash commands</h3>
        <ul className="help-list">
          {CANON_SLASH.map((c) => (
            <li className="help-row" key={c.name}>
              <kbd className="help-chord help-slash">{c.name}</kbd>
              <span className="help-label">{c.desc}</span>
            </li>
          ))}
        </ul>
        <p className="help-foot dim">
          run <code>/commands</code> in the terminal for the full live list, or press
          <kbd className="help-chord help-inline">Ctrl+;</kbd> to label every clickable element.
        </p>
      </section>
    </div>
  );
}
