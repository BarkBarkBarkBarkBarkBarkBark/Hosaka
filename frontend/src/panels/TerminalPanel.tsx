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
    const host = hostRef.current;

    // #region agent log
    const dbg = (window as unknown as { __hosakaDbg?: (loc: string, msg: string, data?: Record<string, unknown>) => void }).__hosakaDbg;
    dbg?.("TerminalPanel.tsx:mount", "TerminalPanel useEffect entry", {
      active,
      hostW: host.offsetWidth,
      hostH: host.offsetHeight,
      parentW: host.parentElement?.offsetWidth,
      parentH: host.parentElement?.offsetHeight,
      grandparentHidden: host.parentElement?.parentElement?.hidden,
      grandparentDisplay: host.parentElement?.parentElement
        ? getComputedStyle(host.parentElement.parentElement).display
        : null,
    });
    // #endregion

    // Determine font size from user preference; fall back to narrow-screen
    // auto-scaling so phones in portrait still fit the banner without wrapping.
    const isNarrow = window.innerWidth < 500;
    const prefSize = FONT_SIZE_TERMINAL[loadUiConfig().fontSize];
    const term = new Terminal({
      fontFamily: '"JetBrains Mono", "Fira Code", Menlo, Consolas, monospace',
      fontSize: isNarrow ? Math.min(prefSize, 12) : prefSize,
      cursorBlink: true,
      cursorStyle: "bar",
      // 5 000 lines burned ~500 KB of RAM on Pi 3B just idling; 1 500 keeps
      // "hours of session" without the weight.
      scrollback: 1500,
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

    termRef.current = term;
    fitRef.current = fit;

    // Defer term.open() until the host actually has non-zero dimensions.
    // Otherwise xterm bakes in a 1×1-ish grid that fit() can't fully recover
    // (the user just sees an unusable black square). This happens whenever
    // TerminalPanel mounts while the panel is hidden (display:none) — for
    // example when stale localStorage keeps activeAppId on a non-terminal
    // surface across the new build's terminal-first boot.
    let opened = false;
    let shell: HosakaShell | null = null;

    const ensureOpened = () => {
      if (opened) return;
      if (host.offsetWidth === 0 || host.offsetHeight === 0) return;
      term.open(host);
      let fitErr: string | null = null;
      try { fit.fit(); } catch (err) { fitErr = err instanceof Error ? err.message : String(err); }
      opened = true;
      shell = new HosakaShell(term);
      shellRef.current = shell;
      shell.start();
      // Defend against xterm capturing an intermediate small layout: re-fit
      // on the next frame after the first open so any late layout work has
      // settled before we lock in cols/rows.
      requestAnimationFrame(() => {
        try { fit.fit(); } catch { /* ignore */ }
        // #region agent log
        dbg?.("TerminalPanel.tsx:raf-refit", "post-open raf fit", {
          hostW: host.offsetWidth,
          hostH: host.offsetHeight,
          cols: term.cols,
          rows: term.rows,
        });
        // #endregion
      });
      // #region agent log
      dbg?.("TerminalPanel.tsx:opened", "deferred xterm open completed", {
        hostW: host.offsetWidth,
        hostH: host.offsetHeight,
        cols: term.cols,
        rows: term.rows,
        fitErr,
      });
      // #endregion
    };

    ensureOpened();

    // Watch the host element so when it transitions from 0×0 (hidden panel)
    // to real dimensions, we open xterm or refit without losing the
    // already-mounted shell instance.
    let roTickCount = 0;
    const ro = new ResizeObserver(() => {
      roTickCount += 1;
      if (!opened) {
        // #region agent log
        dbg?.("TerminalPanel.tsx:ro-pre-open", "RO tick before xterm open", {
          tick: roTickCount,
          hostW: host.offsetWidth,
          hostH: host.offsetHeight,
        });
        // #endregion
        ensureOpened();
        return;
      }
      try { fit.fit(); } catch { /* ignore layout-thrash */ }
      // #region agent log
      dbg?.("TerminalPanel.tsx:ro-post-open", "RO tick after xterm open", {
        tick: roTickCount,
        hostW: host.offsetWidth,
        hostH: host.offsetHeight,
        cols: term.cols,
        rows: term.rows,
      });
      // #endregion
    });
    ro.observe(host);

    // Delayed snapshot: tells us whether host dimensions actually grew past
    // the initial small layout (vs xterm just capturing 22px and never
    // reflowing). 1.5 s is well past Suspense + chunk-load + first paint.
    const delayed = window.setTimeout(() => {
      const xterm = host.querySelector(".xterm") as HTMLElement | null;
      // #region agent log
      dbg?.("TerminalPanel.tsx:delayed", "1.5s post-mount snapshot", {
        opened,
        hostW: host.offsetWidth,
        hostH: host.offsetHeight,
        xtermW: xterm?.offsetWidth ?? null,
        xtermH: xterm?.offsetHeight ?? null,
        cols: term.cols,
        rows: term.rows,
        hostCSS: getComputedStyle(host).cssText.slice(0, 280),
      });
      // #endregion
    }, 1500);

    const onResize = () => {
      try {
        if (opened) fit.fit();
      } catch {
        // ignore layout-thrash errors
      }
    };
    const onUiChanged = () => {
      const isNarrowNow = window.innerWidth < 500;
      const size = FONT_SIZE_TERMINAL[loadUiConfig().fontSize];
      term.options.fontSize = isNarrowNow ? Math.min(size, 12) : size;
      try { if (opened) fit.fit(); } catch { /* ignore */ }
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("hosaka:ui-changed", onUiChanged);

    return () => {
      window.clearTimeout(delayed);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
      window.removeEventListener("hosaka:ui-changed", onUiChanged);
      shell?.dispose();
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
