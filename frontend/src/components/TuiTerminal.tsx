import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { useTranslation } from "../i18n";
import { FONT_SIZE_TERMINAL, loadUiConfig } from "../uiConfig";

export function TuiTerminal({ active, flash, onFlash }: {
  active: boolean;
  flash: string | null;
  onFlash: (text: string | null) => void;
}) {
  const { t } = useTranslation("gui");
  const host = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState("connecting");
  const [detail, setDetail] = useState("");
  const flashRef = useRef(flash);
  flashRef.current = flash;
  const flashButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!host.current) return;
    const mount = host.current;
    setStatus("connecting");
    setDetail("");
    let cleanup = () => {};
    const frame = requestAnimationFrame(() => {
      const term = new Terminal({
        fontFamily: '"JetBrains Mono", Menlo, Consolas, monospace',
        fontSize: FONT_SIZE_TERMINAL[loadUiConfig().fontSize],
        cursorBlink: true,
        scrollback: 1500,
        theme: { background: "#0b0d10", foreground: "#d8dee4", cursor: "#ffbf46" },
      });
      const fit = new FitAddon();
      term.loadAddon(fit);
      term.loadAddon(new WebLinksAddon());
      const flashHandler = term.parser.registerOscHandler(777, (data) => {
        const prefix = "hosaka-flash;";
        if (!data.startsWith(prefix)) return false;
        try {
          const text: unknown = JSON.parse(data.slice(prefix.length));
          if (typeof text !== "string" || !text.trim() || Array.from(text).length > 80 || /[\u0000-\u001f\u007f]/.test(text)) {
            console.error("Invalid /flash terminal payload");
            return true;
          }
          flashRef.current = text;
          onFlash(text);
        } catch (error) {
          console.error("Invalid /flash terminal payload", error);
        }
        return true;
      });
      term.open(mount);
      fit.fit();
      terminal.current = term;
      const url = new URL("/ws/tui", location.href);
      url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
      url.searchParams.set("cols", String(Math.max(20, term.cols)));
      url.searchParams.set("rows", String(Math.max(5, term.rows)));
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      let disposed = false;
      const send = (message: object) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
      };
      ws.onopen = () => {
        if (disposed) return;
        setStatus("connected");
        send({ type: "resize", cols: Math.max(20, term.cols), rows: Math.max(5, term.rows) });
        if (activeRef.current) term.focus();
      };
      ws.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (!disposed) term.write(new Uint8Array(event.data));
      };
      ws.onerror = () => {
        if (!disposed) setStatus("failed");
      };
      ws.onclose = (event) => {
        if (disposed) return;
        setStatus(event.code === 1000 ? "ended" : "failed");
        setDetail(event.reason);
      };
      const input = term.onData((data) => {
        if (activeRef.current && flashRef.current === null) send({ type: "input", data });
      });
      const size = term.onResize(({ cols, rows }) => {
        send({ type: "resize", cols: Math.max(20, cols), rows: Math.max(5, rows) });
      });
      const observer = new ResizeObserver(() => {
        if (!disposed) fit.fit();
      });
      observer.observe(mount);
      const updateFont = () => {
        term.options.fontSize = FONT_SIZE_TERMINAL[loadUiConfig().fontSize];
        fit.fit();
      };
      window.addEventListener("hosaka:ui-changed", updateFont);
      cleanup = () => {
        disposed = true;
        observer.disconnect();
        window.removeEventListener("hosaka:ui-changed", updateFont);
        input.dispose();
        size.dispose();
        flashHandler.dispose();
        ws.close();
        term.dispose();
        terminal.current = null;
      };
    });
    return () => {
      cancelAnimationFrame(frame);
      cleanup();
    };
  }, [attempt, onFlash]);

  useEffect(() => {
    if (active && flash === null) terminal.current?.focus();
    else terminal.current?.blur();
    if (flash !== null) flashButton.current?.focus();
  }, [active, flash]);

  useEffect(() => {
    if (flash === null) return;
    const dismiss = (event: KeyboardEvent) => {
      if (!["Escape", "Enter", " "].includes(event.key)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      flashRef.current = null;
      onFlash(null);
    };
    window.addEventListener("keydown", dismiss, true);
    return () => window.removeEventListener("keydown", dismiss, true);
  }, [flash, onFlash]);

  return (
    <section className="native-tui" aria-label={t("terminal")}>
      <div className="native-tui-host" ref={host} />
      {flash !== null && (
        <button
          ref={flashButton}
          className="deck-flash"
          aria-label={t("flashDismiss")}
          onClick={() => { flashRef.current = null; onFlash(null); }}
        >
          <span className="deck-flash-word">{flash}</span>
        </button>
      )}
      {status !== "connected" && (
        <div className="native-tui-status" role="status">
          <span>{t(`status.${status}`)} {detail}</span>
          {status !== "connecting" && (
            <button onClick={() => setAttempt((value) => value + 1)}>{t("reconnect")}</button>
          )}
        </div>
      )}
    </section>
  );
}
