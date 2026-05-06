/**
 * ExternalAppPanel — generic surface for flatpak-backed Hosaka apps.
 *
 * One panel handles all of: spotify, discord, foliate, vscode, firefox,
 * telegram, betterbird, alienarena, slack, steam (and any future flatpak
 * manifest under hosaka-apps/apps/).
 *
 * Behavior:
 *   - On mount, fetches /api/v1/apps/{id}/status and capabilities.
 *   - Renders install button if not installed, launch button if installed.
 *   - Esc → "are you sure you want to exit?" confirm modal → closeApp(appId).
 *     If the launched flatpak window is still open on the host, this only
 *     closes the Hosaka tab; the OS window stays where it is.
 *   - Ctrl+O is left to the global shortcut handler (toggle orb).
 *   - Linux gating happens at the registry level; this panel still renders
 *     a graceful "not available on this host" notice if capabilities say so.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getHosakaAppCapabilities,
  getHosakaAppStatus,
  installHosakaApp,
  launchHosakaApp,
  type HosakaAppCapabilities,
  type HosakaAppHostResponse,
} from "../apps/flatpakBackend";
import { getHosakaAppById, type HosakaAppManifest } from "../apps/hosakaApps";
import { getAppDefinition, type AppId } from "../ui/appRegistry";

type Props = {
  appId: AppId;
  onClose: (appId: AppId) => void;
};

type Phase = "loading" | "ready" | "installing" | "launching" | "error";

export function ExternalAppPanel({ appId, onClose }: Props) {
  const definition = getAppDefinition(appId);
  const manifest: HosakaAppManifest | null = getHosakaAppById(appId);
  const [phase, setPhase] = useState<Phase>("loading");
  const [status, setStatus] = useState<HosakaAppHostResponse | null>(null);
  const [caps, setCaps] = useState<HosakaAppCapabilities | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const lastMessageRef = useRef<string>("");

  const refresh = useCallback(async () => {
    setPhase("loading");
    const [s, c] = await Promise.all([
      getHosakaAppStatus(appId),
      getHosakaAppCapabilities(),
    ]);
    setStatus(s);
    setCaps(c);
    setPhase(s.ok ? "ready" : "error");
    lastMessageRef.current = s.message;
  }, [appId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Esc → confirm-quit modal (unless an input has focus elsewhere).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || t?.isContentEditable) return;
      // only act if this panel is in the active subtree
      const host = document.querySelector(`.external-app-panel[data-app="${appId}"]`);
      if (!host || !host.closest(".hosaka-panel.is-active")) return;
      e.stopPropagation();
      setConfirmOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [appId]);

  async function handleInstall() {
    setPhase("installing");
    const res = await installHosakaApp(appId);
    setStatus(res);
    setPhase(res.ok ? "ready" : "error");
    if (res.ok) void refresh();
  }

  async function handleLaunch() {
    setPhase("launching");
    const res = await launchHosakaApp(appId);
    setStatus(res);
    setPhase(res.ok ? "ready" : "error");
  }

  const title = definition?.title ?? manifest?.name ?? appId;
  const glyph = definition?.glyph ?? "▢";
  const description = definition?.description ?? manifest?.description ?? "";
  const flatpakId = manifest?.flatpak_id ?? "—";
  const installed = Boolean(status?.installed);
  const flatpakAvailable = caps?.flatpakAvailable ?? false;
  const mocked = caps?.mocked ?? false;
  const installCmd = manifest?.install.command.join(" ") ?? "";
  const launchCmd = manifest?.launch.command.join(" ") ?? "";

  // Arch compat: registry says which arches Flathub publishes, capabilities
  // says what arch the host actually is. Mismatch = install button is futile.
  const declaredArches = definition?.flatpakArches ?? [];
  const hostArch = (status?.hostArch ?? caps?.arch ?? "").toLowerCase();
  const archIncompatible = Boolean(
    status?.archIncompatible ||
    (declaredArches.length > 0 && hostArch && !declaredArches.includes(hostArch as never)),
  );
  const supportedArches = status?.supportedArches ?? declaredArches;

  return (
    <div className="desktop-panel external-app-panel" data-app={appId}>
      <div className="panel-header">
        <h2><span className="panel-glyph">{glyph}</span> {title}</h2>
        <p className="panel-sub">
          {description}
        </p>
      </div>

      <div style={{ padding: "0 1rem 0.75rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        <div className="dim" style={{ fontSize: "0.85em" }}>
          flatpak · <code>{flatpakId}</code>
          {manifest?.memory.profile ? ` · memory: ${manifest.memory.profile}` : ""}
        </div>

        {!caps && <div className="dim">checking host capabilities…</div>}

        {caps && !flatpakAvailable && (
          <div className="banner banner--warn" style={{ padding: "0.5rem 0.75rem", border: "1px solid rgba(255,180,90,0.3)", borderRadius: 4 }}>
            <strong>flatpak unavailable on this host.</strong>{" "}
            {caps.note ?? "this app needs a Linux host with flatpak + flathub configured."}
            {mocked && " (running in mock mode — install/launch are simulated.)"}
          </div>
        )}

        {caps && flatpakAvailable && caps.flathubConfigured === false && (
          <div className="banner banner--warn" style={{ padding: "0.5rem 0.75rem", border: "1px solid rgba(255,180,90,0.3)", borderRadius: 4 }}>
            <strong>flathub remote missing.</strong> {caps.note}
          </div>
        )}

        {archIncompatible && (
          <div
            className="banner banner--warn"
            style={{ padding: "0.5rem 0.75rem", border: "1px solid rgba(255,120,120,0.4)", borderRadius: 4, background: "rgba(255,120,120,0.06)" }}
          >
            <strong>won't run on this device.</strong>{" "}
            <code>{flatpakId}</code> is published for{" "}
            <code>{supportedArches.join(", ") || "x86_64"}</code> only on Flathub.
            this host is <code>{hostArch || "unknown"}</code> (e.g. Raspberry Pi 3B+/4 = aarch64).
            <div className="dim" style={{ marginTop: "0.35rem", fontSize: "0.85em" }}>
              there is no upstream aarch64 build today. install is disabled to avoid a confusing failure.
            </div>
          </div>
        )}

        {phase === "loading" && <div className="dim">loading status…</div>}

        {status && phase !== "loading" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <div>
              status:{" "}
              <strong style={{ color: installed ? "#9cf" : "#fc8" }}>
                {installed ? "installed" : "not installed"}
              </strong>
              {status.host && <span className="dim"> · host: {status.host}</span>}
            </div>
            {status.message && (
              <div className="dim" style={{ fontSize: "0.9em" }}>{status.message}</div>
            )}
            {status.actionableCommand && (
              <code style={{ fontSize: "0.85em", opacity: 0.75 }}>{status.actionableCommand}</code>
            )}
          </div>
        )}

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn"
            disabled={phase === "installing" || phase === "launching" || installed || archIncompatible}
            title={archIncompatible ? "not available for this CPU architecture" : undefined}
            onClick={() => void handleInstall()}
          >
            {phase === "installing" ? "installing…" : installed ? "installed" : archIncompatible ? "unavailable" : "install"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={phase === "installing" || phase === "launching" || !installed}
            onClick={() => void handleLaunch()}
          >
            {phase === "launching" ? "launching…" : "launch"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => void refresh()}
            disabled={phase === "loading"}
          >
            refresh
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setConfirmOpen(true)}
            title="close this hosaka tab (esc)"
          >
            close tab
          </button>
        </div>

        <details style={{ marginTop: "0.5rem" }}>
          <summary className="dim" style={{ cursor: "pointer" }}>commands &amp; permissions</summary>
          <div style={{ paddingTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.85em" }}>
            <div><span className="dim">install:</span> <code>{installCmd}</code></div>
            <div><span className="dim">launch:</span> <code>{launchCmd}</code></div>
            {manifest?.permissions_notes?.length ? (
              <ul style={{ margin: "0.25rem 0 0 1rem", padding: 0 }}>
                {manifest.permissions_notes.map((n, i) => <li key={i} className="dim">{n}</li>)}
              </ul>
            ) : null}
            {manifest?.account_login_required && (
              <div className="dim">⚐ account login required — hosaka does not store credentials.</div>
            )}
          </div>
        </details>
      </div>

      {confirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="confirm exit"
          className="external-app-confirm"
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(0,0,0,0.55)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 50,
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setConfirmOpen(false); }}
        >
          <div
            style={{
              background: "#111",
              border: "1px solid rgba(255,255,255,0.15)",
              borderRadius: 6,
              padding: "1rem 1.25rem",
              minWidth: 280,
              maxWidth: 420,
            }}
          >
            <div style={{ marginBottom: "0.75rem" }}>
              close <strong>{title}</strong>?
            </div>
            <div className="dim" style={{ fontSize: "0.85em", marginBottom: "1rem" }}>
              this only closes the hosaka tab. if {title} is already running, its window stays open on the desktop.
            </div>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
              <button type="button" className="btn" onClick={() => setConfirmOpen(false)}>cancel</button>
              <button
                type="button"
                className="btn"
                autoFocus
                onClick={() => { setConfirmOpen(false); onClose(appId); }}
              >yes, close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
