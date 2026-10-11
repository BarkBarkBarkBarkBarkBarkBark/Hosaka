/**
 * CmdLine — always-visible single-line command strip.
 *
 * Sits beneath the stage and above the footer. Typing here and pressing
 * Enter sends `hosaka:terminal-stage-command` (autoSubmit). Empty Enter
 * focuses the terminal panel. Up/Down recall the local history (this
 * strip's own ring, separate from xterm scrollback).
 *
 * It's NOT a substitute for the full terminal — it's a quick keyboard-only
 * way to fire a slash command without leaving whatever panel you're in.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { executeHosakaUiCommand } from "../ui/hosakaUi";

const HISTORY_KEY = "hosaka.cmdline.history";
const MAX_HISTORY = 50;

function loadHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((s) => typeof s === "string") : [];
  } catch { return []; }
}

function saveHistory(h: string[]): void {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(-MAX_HISTORY))); } catch { /* quota */ }
}

export function CmdLine() {
  const [value, setValue] = useState("");
  const [history, setHistory] = useState<string[]>(() => loadHistory());
  const [, setCursor] = useState<number>(-1); // -1 = editing
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Allow other components (e.g. shortcut Ctrl+T) to focus the strip.
  useEffect(() => {
    const onFocus = () => inputRef.current?.focus();
    window.addEventListener("hosaka:cmdline-focus", onFocus);
    return () => window.removeEventListener("hosaka:cmdline-focus", onFocus);
  }, []);

  // Allow agents (or any code path) to suggest a command. The human still
  // presses Enter unless `submit: true` is passed. This is the channel for
  // "orb proposes a fix" or "correct the previous mis-typed command" UX.
  useEffect(() => {
    const onPrefill = (e: Event) => {
      const detail = (e as CustomEvent<{ text?: string; submit?: boolean; focus?: boolean }>).detail || {};
      const text = String(detail.text ?? "");
      if (!text) return;
      setValue(text);
      setCursor(-1);
      if (detail.focus !== false) {
        const el = inputRef.current;
        if (el) {
          el.focus();
          // place caret at end so Enter just runs it
          requestAnimationFrame(() => {
            try { el.setSelectionRange(text.length, text.length); } catch { /* ignore */ }
          });
        }
      }
      if (detail.submit) {
        // give React a tick to flush the value before submitting
        queueMicrotask(() => {
          executeHosakaUiCommand({ id: "ui.stage_terminal_command", command: text, autoSubmit: true });
          setHistory((prev) => {
            const next = prev[prev.length - 1] === text ? prev : [...prev, text];
            saveHistory(next);
            return next;
          });
          setValue("");
        });
      }
    };
    window.addEventListener("hosaka:cmdline-prefill", onPrefill as EventListener);
    return () => window.removeEventListener("hosaka:cmdline-prefill", onPrefill as EventListener);
  }, []);

  const submit = useCallback(() => {
    const text = value.trim();
    if (!text) {
      // empty submit: focus terminal panel
      executeHosakaUiCommand({ id: "ui.focus_terminal" });
      return;
    }
    executeHosakaUiCommand({ id: "ui.stage_terminal_command", command: text, autoSubmit: true });
    setHistory((prev) => {
      const next = prev[prev.length - 1] === text ? prev : [...prev, text];
      saveHistory(next);
      return next;
    });
    setValue("");
    setCursor(-1);
  }, [value]);

  const recall = useCallback((delta: number) => {
    if (history.length === 0) return;
    setCursor((prev) => {
      const idx = prev === -1 ? history.length : prev;
      const next = Math.min(history.length, Math.max(0, idx + delta));
      setValue(next === history.length ? "" : history[next]);
      return next === history.length ? -1 : next;
    });
  }, [history]);

  const onKey = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submit();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      recall(-1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      recall(+1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setValue("");
      setCursor(-1);
      (e.currentTarget as HTMLInputElement).blur();
    }
  }, [submit, recall]);

  return (
    <div className="hosaka-cmdline" role="search">
      <span className="hosaka-cmdline-prompt" aria-hidden>›</span>
      <input
        ref={inputRef}
        type="text"
        className="hosaka-cmdline-input"
        placeholder="type a command, then enter — Ctrl+T for the full terminal · Ctrl+/ for help"
        value={value}
        onChange={(e) => { setValue(e.target.value); setCursor(-1); }}
        onKeyDown={onKey}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        aria-label="quick command line"
        data-hint="cmdline"
      />
      <button
        type="button"
        className="hosaka-cmdline-go"
        onClick={submit}
        aria-label="run command"
        title="run (enter)"
        data-hint="cmdline-run"
      >↵</button>
    </div>
  );
}
