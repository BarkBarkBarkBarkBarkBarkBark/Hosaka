import React, { Component, Suspense, type ErrorInfo, type ReactNode } from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./ui/hosakaUi";
import { bootTheme } from "./ui/theme";
import { executeHosakaUiCommand } from "./ui/hosakaUi";
import "./styles/app.css";

// Apply persisted theme before React mounts so we never flash the default.
bootTheme();

// Expose a tiny global so any agent (picoclaw, devtools, e2e) can suggest
// commands into the always-on cmdline. The human still presses Enter unless
// `submit: true` is passed. Keep the surface small on purpose.
(window as unknown as {
  hosakaSuggest?: (text: string, opts?: { submit?: boolean; focus?: boolean }) => void;
}).hosakaSuggest = (text, opts = {}) => {
  executeHosakaUiCommand({
    id: "ui.prefill_cmdline",
    text,
    submit: Boolean(opts.submit),
    focus: opts.focus !== false,
  });
};

// #region agent log
function dbg(location: string, message: string, data: Record<string, unknown> = {}) {
  try {
    fetch("http://localhost:7689/ingest/1a43a65d-59a9-4e4d-b675-be2f9e8f84bd", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "860fc3" },
      body: JSON.stringify({
        sessionId: "860fc3",
        location,
        message,
        data,
        timestamp: Date.now(),
      }),
    }).catch(() => {});
  } catch { /* ignore */ }
}
(window as unknown as { __hosakaDbg?: typeof dbg }).__hosakaDbg = dbg;
dbg("main.tsx:boot", "main module loaded", {
  href: location.href,
  ua: navigator.userAgent.slice(0, 120),
  ls_windows: (() => { try { return localStorage.getItem("hosaka.sync.windows"); } catch { return null; } })(),
  ls_overlays: (() => { try { return localStorage.getItem("hosaka.sync.overlays"); } catch { return null; } })(),
});
// #endregion

function bootFailure(message: string, detail?: unknown) {
  const root = document.getElementById("root");
  if (!root || root.childNodes.length > 0) return;
  const text = detail instanceof Error
    ? `${detail.name}: ${detail.message}\n${detail.stack ?? ""}`
    : typeof detail === "string"
      ? detail
      : detail
        ? JSON.stringify(detail, null, 2)
        : "";
  root.innerHTML = `
    <div style="min-height:100vh;box-sizing:border-box;padding:32px;background:#0b0d10;color:#f3e9c1;font:14px ui-monospace,SFMono-Regular,Menlo,monospace">
      <h1 style="margin:0 0 12px;color:#ffbf46;font-size:18px">Hosaka renderer failed to mount</h1>
      <p style="margin:0 0 16px;color:#9aa4b2">${message}</p>
      <pre style="white-space:pre-wrap;background:#141820;border:1px solid #30384a;border-radius:10px;padding:14px;overflow:auto;max-height:60vh">${text.replace(/[<&>]/g, (ch) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[ch] ?? ch))}</pre>
      <p style="margin-top:16px;color:#9aa4b2">Open the console and copy the red error above. Signal no longer hides in a black box.</p>
    </div>`;
}

window.addEventListener("error", (event) => {
  // #region agent log
  dbg("main.tsx:error", "window error", {
    msg: event.message,
    file: event.filename,
    line: event.lineno,
    col: event.colno,
    stack: event.error instanceof Error ? event.error.stack?.slice(0, 800) : null,
  });
  // #endregion
  bootFailure(event.message, event.error ?? event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  // #region agent log
  dbg("main.tsx:rejection", "unhandled promise rejection", {
    reason: event.reason instanceof Error ? `${event.reason.name}: ${event.reason.message}\n${event.reason.stack?.slice(0, 600)}` : String(event.reason).slice(0, 800),
  });
  // #endregion
  bootFailure("Unhandled promise rejection", event.reason);
});
setTimeout(() => bootFailure("React did not mount within 5 seconds."), 5000);

class BootErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Hosaka render error", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ minHeight: "100vh", boxSizing: "border-box", padding: 32, background: "#0b0d10", color: "#f3e9c1", font: "14px ui-monospace, SFMono-Regular, Menlo, monospace" }}>
        <h1 style={{ margin: "0 0 12px", color: "#ffbf46", fontSize: 18 }}>Hosaka renderer crashed</h1>
        <p style={{ margin: "0 0 16px", color: "#ff8787" }}>
          {this.state.error.name}: {this.state.error.message}
        </p>
        <pre style={{ whiteSpace: "pre-wrap", background: "#141820", border: "1px solid #30384a", borderRadius: 10, padding: 14, overflow: "auto", maxHeight: "70vh" }}>
          {this.state.error.stack ?? `${this.state.error.name}: ${this.state.error.message}`}
        </pre>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BootErrorBoundary>
      <Suspense fallback={null}>
        <App />
      </Suspense>
    </BootErrorBoundary>
  </React.StrictMode>,
);
