import { useEffect, useState } from "react";

/** Tiny header widget: shows current mode + lets the operator flip to the
 *  other one with a confirm dialog. Talks to the documented `/api/v1/mode`
 *  endpoints — same contract as hosakactl and the /device page. */

type Mode = "console" | "device";

const OTHER: Record<Mode, Mode> = { console: "device", device: "console" };
const COPY: Record<Mode, { label: string; explain: string }> = {
  console: {
    label: "switch to console",
    explain:
      "Brings the touchscreen kiosk back on the Pi. Picoclaw + Chromium restart. Roughly 5 seconds.",
  },
  device: {
    label: "switch to device",
    explain:
      "Stops the kiosk and shows the diagnostic dashboard on the Pi's TTY. Frees ~600 MB so SSH stays responsive. The web UI keeps running but this tab will go offline visually.",
  },
};

export function ModeSwitch() {
  const [mode, setMode] = useState<Mode | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    fetch("/api/v1/mode")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => { if (!cancel) setMode(j.mode); })
      .catch(() => { /* API not deployed yet — hide */ });
    return () => { cancel = true; };
  }, []);

  if (!mode) return null;
  const next = OTHER[mode];
  const copy = COPY[next];

  async function flip(persist: boolean) {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/v1/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: next, persist }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setMode(j.mode);
      setConfirming(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        className="icon-btn mode-switch-btn"
        onClick={() => setConfirming(true)}
        title={`current: ${mode} — click to ${copy.label}`}
        aria-label={copy.label}
      >
        <span className={`mode-dot mode-dot--${mode}`} aria-hidden />
        <span className="mode-label">{mode}</span>
      </button>

      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          className="mode-switch-overlay"
          onClick={(e) => e.target === e.currentTarget && setConfirming(false)}
        >
          <div className="mode-switch-modal">
            <h2>{copy.label}?</h2>
            <p>{copy.explain}</p>
            {err && <p className="mode-switch-err">error: {err}</p>}
            <div className="mode-switch-actions">
              <button onClick={() => setConfirming(false)} disabled={busy}>cancel</button>
              <button onClick={() => flip(false)} disabled={busy}>
                {busy ? "switching…" : "this boot only"}
              </button>
              <button className="primary" onClick={() => flip(true)} disabled={busy}>
                {busy ? "switching…" : "and persist"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
