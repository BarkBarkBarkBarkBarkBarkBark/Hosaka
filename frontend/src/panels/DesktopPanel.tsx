import type { ConversationEntry } from "../chat/conversationLog";
import {
  HOST_LABELS,
  INSTALL_LABELS,
  type AppDefinition,
  type AppId,
} from "../ui/appRegistry";

export type DesktopPanelProps = {
  mode?: "desktop" | "directory";
  apps: AppDefinition[];
  openAppIds: AppId[];
  activeAppId: AppId;
  conversation: ConversationEntry[];
  onOpenApp: (appId: AppId) => void;
  onCloseApp: (appId: AppId) => void;
  onStageCommand: (command: string, autoSubmit?: boolean) => void;
};

export function DesktopPanel({
  mode = "desktop",
  apps,
  openAppIds,
  activeAppId,
  conversation,
  onOpenApp,
  onCloseApp,
  onStageCommand,
}: DesktopPanelProps) {
  const recent = conversation
    .filter((entry) => entry.visibility === "visible")
    .slice(-8)
    .reverse();
  const featured = mode === "desktop"
    ? apps.filter((app) => ["home", "terminal", "workbench", "voice", "web", "wiki", "video", "tool_directory"].includes(app.id))
    : apps;

  return (
    <div className={`desktop-panel desktop-panel--${mode}`}>
      <div className="panel-header">
        <h2>
          <span className="panel-glyph">⌂</span> {mode === "desktop" ? "desktop" : "app directory"}
        </h2>
        <p className="panel-sub">
          {mode === "desktop"
            ? "launch surfaces, resume open windows, and keep the deck feeling like a home screen."
            : "electron-first apps, browser fallback, with external app integrations planned soon."}
        </p>
      </div>

      <div className="desktop-hero">
        <div className="desktop-hero-copy">
          <strong>signal steady</strong>
          <span>{openAppIds.length} windows open · active: {activeAppId}</span>
        </div>
        <div className="desktop-hero-actions">
          <button className="btn btn-primary" onClick={() => onOpenApp("terminal")}>open terminal</button>
          <button className="btn btn-ghost" onClick={() => onOpenApp("workbench")}>open workbench</button>
          <button className="btn btn-ghost" onClick={() => onStageCommand("/launch voice")}>stage /launch voice</button>
        </div>
      </div>

      <section className="desktop-grid" aria-label="apps">
        {featured.map((app) => {
          const open = openAppIds.includes(app.id);
          const launchable = app.status !== "planned";
          return (
            <article key={app.id} className={`desktop-card ${open ? "is-open" : ""}`}>
              <div className="desktop-card-head">
                <div>
                  <strong>{app.glyph} {app.title}</strong>
                  <p>{app.description}</p>
                </div>
                {open && <span className="desktop-state">open</span>}
              </div>
              {mode === "directory" && (
                <div className="desktop-card-meta">
                  {app.family && <span className="desktop-badge">{app.family}</span>}
                  {app.status && <span className="desktop-badge">{app.status}</span>}
                  {app.preferredHost && <span className="desktop-badge">{HOST_LABELS[app.preferredHost]}</span>}
                  {app.installStrategy && <span className="desktop-badge">{INSTALL_LABELS[app.installStrategy]}</span>}
                </div>
              )}
              {mode === "directory" && (app.maintainerNote || app.agentNote) && (
                <div className="desktop-card-notes">
                  {app.maintainerNote && (
                    <p>
                      <strong>owner:</strong> {app.maintainerNote}
                    </p>
                  )}
                  {app.agentNote && (
                    <p>
                      <strong>ai:</strong> {app.agentNote}
                    </p>
                  )}
                </div>
              )}
              <div className="desktop-card-actions">
                <button className="btn btn-primary" onClick={() => onOpenApp(app.id)} disabled={!launchable}>
                  {launchable ? (open ? "resume" : "launch") : "planned"}
                </button>
                {open && app.closable !== false && (
                  <button className="btn btn-ghost" onClick={() => onCloseApp(app.id)}>
                    close
                  </button>
                )}
                <button className="btn btn-ghost" onClick={() => onStageCommand(`/launch ${app.id}`)}>
                  stage cmd
                </button>
              </div>
            </article>
          );
        })}
      </section>

      <section className="desktop-bottom-grid">
        <article className="desktop-card desktop-card--wide">
          <div className="desktop-card-head">
            <div>
              <strong>open windows</strong>
              <p>horizontal tabs above mirror these runtime windows.</p>
            </div>
          </div>
          <div className="desktop-window-list">
            {openAppIds.map((appId) => {
              const app = apps.find((entry) => entry.id === appId);
              if (!app) return null;
              return (
                <button
                  key={appId}
                  className={`desktop-window-pill ${activeAppId === appId ? "is-active" : ""}`}
                  onClick={() => onOpenApp(appId)}
                >
                  {app.glyph} {app.title}
                </button>
              );
            })}
          </div>
        </article>

        <article className="desktop-card desktop-card--wide">
          <div className="desktop-card-head">
            <div>
              <strong>recent conversation</strong>
              <p>shared text + voice log, ready for hidden/internal entries later.</p>
            </div>
          </div>
          <div className="desktop-conversation-preview">
            {recent.length === 0 && <div className="dim">no shared history yet.</div>}
            {recent.map((entry) => (
              <div key={entry.id} className={`desktop-log-entry role-${entry.role}`}>
                <span>{entry.source}</span>
                <strong>{entry.role}</strong>
                <p>{entry.text}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}
