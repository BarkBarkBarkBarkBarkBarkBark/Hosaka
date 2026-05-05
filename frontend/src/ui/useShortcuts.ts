/**
 * useShortcuts — installs a single capture-phase keydown listener that
 * dispatches HosakaUiCommands when a registered chord is pressed.
 *
 * The hook also exposes a "hint mode" event handler so the HintLayer can
 * react to Ctrl+; without colliding with normal text entry. We treat the
 * terminal canvas (xterm) as non-typing because xterm has its own
 * attachCustomKeyEventHandler bypass (see TerminalPanel).
 */
import { useEffect } from "react";
import { matchShortcut } from "./shortcuts";
import { executeHosakaUiCommand } from "./hosakaUi";

const HINT_EVENT = "hosaka:hint-toggle";

function isTypingTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  if (t.isContentEditable) return true;
  const tag = t.tagName;
  if (tag === "INPUT") {
    const type = (t as HTMLInputElement).type;
    // checkbox/radio/etc. don't capture text, so chords still work there
    return type !== "checkbox" && type !== "radio" && type !== "button" && type !== "submit";
  }
  return tag === "TEXTAREA" || tag === "SELECT";
}

export function useShortcuts(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = isTypingTarget(e.target);
      const hit = matchShortcut(e, typing);
      if (!hit) return;
      e.preventDefault();
      e.stopPropagation();
      // hint layer is a UI-only command we route through a dedicated event
      if (hit.command.id === "ui.open_panel" && hit.command.target === "__hint__") {
        window.dispatchEvent(new CustomEvent(HINT_EVENT));
        return;
      }
      executeHosakaUiCommand(hit.command);
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true } as EventListenerOptions);
  }, []);
}

export const HINT_TOGGLE_EVENT = HINT_EVENT;
