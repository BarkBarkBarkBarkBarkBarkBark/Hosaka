/**
 * DiagOverlay — compact diagnostics summary that hangs above the terminal.
 *
 * Shows the peripherals pill strip + network primary + memory/disk, plus
 * a link to open the full DiagnosticsPanel for the deep dive. Polls
 * /api/v1/diag/snapshot only while open.
 */
import { useCallback, useEffect, useState } from "react";
// Aliased import: a previous build produced a chunk where the rollup output
// dropped the `fetchDiagSnapshot` named import while keeping its call sites,
// causing `ReferenceError: fetchDiagSnapshot is not defined` at runtime
// (verified in /home/operator/.cursor/debug-860fc3.log). Renaming the binding
// forces fresh chunk hashing and side-steps the mis-shaken named import.
import { fetchDiagSnapshot as fetchSnap, statusClass } from "../diagPrimitives";

type Snapshot = {
  ok?: boolean;
  hostname?: string;
  mode?: string;
  generated_at?: string;
  system?: Record<string, any>;
  network?: Record<string, any>;
  peripherals?: Record<string, any>;
};

export function DiagOverlay({ onClose: _onClose }: { onClose: () => void }) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setSnap((await fetchSnap()) as Snapshot | null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    // 30 s cadence + visibilitychange gating. The overlay used to refresh
    // every 6 s which (a) churned the CPU on the Pi 3B+ and (b) re-flowed
    // the meter row whenever a number's digit-count changed.
    let id: number | null = null;
    const start = () => {
      if (id != null) return;
      id = window.setInterval(() => void refresh(), 30000);
    };
    const stop = () => {
      if (id != null) { window.clearInterval(id); id = null; }
    };
    if (document.visibilityState === "visible") start();
    const onVis = () => {
      if (document.visibilityState === "visible") {
        void refresh();
        start();
      } else {
        stop();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refresh]);

  const per = (snap?.peripherals ?? {}) as Record<string, any>;
  const primary = ((snap?.network?.primary ?? {}) as Record<string, any>);
  const mem = ((snap?.system?.mem ?? {}) as Record<string, any>);
  const names: { name: string; item: any }[] = [
    { name: "audio", item: per.audio },
    { name: "video", item: per.video },
    { name: "usb", item: per.usb },
    { name: "bluetooth", item: per.bluetooth },
    { name: "battery", item: per.battery },
  ];

  return (
    <div className="instrument">
      <div className="instrument-row">
        <span className={`instrument-dot ${statusClass(snap?.ok)}`} />
        <span className="instrument-label">host</span>
        <span className="instrument-value">{snap?.hostname ?? "—"}</span>
        <span className="instrument-label" style={{ marginLeft: 10 }}>mode</span>
        <span className="instrument-value">{snap?.mode ?? "—"}</span>
      </div>

      <div className="instrument-row">
        <span className="instrument-label">net</span>
        <span className="instrument-value">{primary.ip ?? primary.tailscale_ip ?? "no ip"}</span>
        <span className="instrument-label" style={{ marginLeft: 10 }}>iface</span>
        <span className="instrument-value">{primary.iface ?? "—"}</span>
      </div>

      <div className="instrument-row">
        <span className="instrument-label">mem</span>
        <span className="instrument-value">{mem.used_mb ?? "—"} / {mem.total_mb ?? "—"} MB</span>
      </div>

      <div className="instrument-row" style={{ gap: 6 }}>
        {names.map(({ name, item }) => {
          const available = Boolean((item as Record<string, any> | undefined)?.available);
          return (
            <span key={name} className="instrument-row" style={{ gap: 4 }}>
              <span className={`instrument-dot ${available ? "is-ok" : "is-warn"}`} />
              <span className="instrument-value">{name}</span>
            </span>
          );
        })}
      </div>

      <div className="instrument-actions">
        <button
          type="button"
          className="instrument-btn"
          onClick={() => void refresh()}
          disabled={loading}
        >{loading ? "scanning…" : "refresh"}</button>
        <button
          type="button"
          className="instrument-btn"
          onClick={() => window.dispatchEvent(new CustomEvent("hosaka:open-app", { detail: { appId: "diagnostics" } }))}
        >open full devices panel</button>
      </div>
    </div>
  );
}
