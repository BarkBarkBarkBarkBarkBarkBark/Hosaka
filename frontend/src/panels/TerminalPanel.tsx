import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
// Co-located with the panel so xterm CSS only ships in the lazy terminal chunk
// (it's ~6 KB on its own). The panel is React.lazy'd from App.tsx, so first
// paint of the kiosk doesn't pay this cost.
import "@xterm/xterm/css/xterm.css";
import { HosakaShell } from "../shell/HosakaShell";
import { loadUiConfig, FONT_SIZE_TERMINAL } from "../uiConfig";

type Props = { active: boolean };

export function TerminalPanel({ active }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const shellRef = useRef<HosakaShell | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;

    // Determine font size from user preference; fall back to narrow-screen
    // auto-scaling so phones in portrait still fit the banner without wrapping.
    const isNarrow = window.innerWidth < 500;
    const prefSize = FONT_SIZE_TERMINAL[loadUiConfig().fontSize];
    const term = new Terminal({
      fontFamily: '"JetBrains Mono", "Fira Code", Menlo, Consolas, monospace',
      fontSize: isNarrow ? Math.min(prefSize, 12) : prefSize,
      cursorBlink: true,
      cursorStyle: "bar",
      scrollback: 5000,
      allowProposedApi: true,
      macOptionIsMeta: true,
      theme: {
        background: "#0b0d10",
        foreground: "#d8dee4",
        cursor: "#ffbf46",
        cursorAccent: "#0b0d10",
        selectionBackground: "#3a2f1a",
        black: "#0b0d10",
        red: "#ff6b6b",
        green: "#7ee787",
        yellow: "#ffbf46",
        blue: "#58a6ff",
        magenta: "#c779ff",
        cyan: "#79ffe1",
        white: "#d8dee4",
        brightBlack: "#5b626b",
        brightRed: "#ff8787",
        brightGreen: "#9cf3a4",
        brightYellow: "#ffd479",
        brightBlue: "#79b8ff",
        brightMagenta: "#d8a7ff",
        brightCyan: "#a8fff0",
        brightWhite: "#f2f4f8",
      },
    });

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(hostRef.current);
    fit.fit();

    const shell = new HosakaShell(term);
    shell.start();

    termRef.current = term;
    fitRef.current = fit;
    shellRef.current = shell;

    const onResize = () => {
      try {
        fit.fit();
      } catch {
        // ignore layout-thrash errors
      }
    };
    const onUiChanged = () => {
      const isNarrowNow = window.innerWidth < 500;
      const size = FONT_SIZE_TERMINAL[loadUiConfig().fontSize];
      term.options.fontSize = isNarrowNow ? Math.min(size, 12) : size;
      try { fit.fit(); } catch { /* ignore */ }
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("hosaka:ui-changed", onUiChanged);

    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("hosaka:ui-changed", onUiChanged);
      term.dispose();
    };
  }, []);

  useEffect(() => {
    if (active && fitRef.current) {
      requestAnimationFrame(() => {
        try {
          fitRef.current?.fit();
          termRef.current?.focus();
        } catch {
          // no-op
        }
      });
    }
  }, [active]);

  return (
    <div className="terminal-wrap">
      <div
        className="terminal-host"
        ref={hostRef}
        onTouchStart={() => termRef.current?.focus()}
      />
    </div>
  );
}
