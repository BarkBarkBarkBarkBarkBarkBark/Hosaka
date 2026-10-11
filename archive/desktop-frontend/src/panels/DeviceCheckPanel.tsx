/**
 * DeviceCheckPanel — wraps a device-check instrument (mic/cam/spk) so it
 * renders as a real tab/panel inside the window manager rather than a
 * floating SurfaceWindow. Same component children, no internal scroll.
 */
import { lazy, Suspense } from "react";

const MicCheckWindow = lazy(() =>
  import("./overlays/MicCheckWindow").then((m) => ({ default: m.MicCheckWindow })),
);
const CamCheckWindow = lazy(() =>
  import("./overlays/CamCheckWindow").then((m) => ({ default: m.CamCheckWindow })),
);
const SpkCheckWindow = lazy(() =>
  import("./overlays/SpkCheckWindow").then((m) => ({ default: m.SpkCheckWindow })),
);

type Kind = "mic" | "cam" | "spk";

export function DeviceCheckPanel({ kind, onClose }: { kind: Kind; onClose: () => void }) {
  const Body = kind === "mic" ? MicCheckWindow : kind === "cam" ? CamCheckWindow : SpkCheckWindow;
  const label = kind === "mic" ? "microphone" : kind === "cam" ? "camera" : "speaker";
  return (
    <div className="device-check-panel">
      <header className="panel-header">
        <h2>
          <span className="panel-glyph">{kind === "mic" ? "🎙" : kind === "cam" ? "📷" : "🔊"}</span>
          {" "}{label} check
        </h2>
        <p className="panel-sub">live preview · close this tab to release the device.</p>
      </header>
      <div className="device-check-body">
        <Suspense fallback={<div className="dim">loading instrument…</div>}>
          <Body onClose={onClose} />
        </Suspense>
      </div>
    </div>
  );
}
