import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "./i18n";
import { PlantBadge } from "./components/PlantBadge";
import { SignalBadge } from "./components/SignalBadge";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { LangPicker } from "./components/LangPicker";
import { ModeSwitch } from "./components/ModeSwitch";
import { applyFontSize, loadUiConfig } from "./uiConfig";
import { FloatingOrb } from "./components/FloatingOrb";
import { useSyncedDoc } from "./sync/useSyncedDoc";
import { useConversationLog } from "./chat/conversationLog";
import {
  APP_REGISTRY,
  getAppDefinition,
  listEnabledApps,
  resolveAppId,
  type AppId,
} from "./ui/appRegistry";
import { dedupeAppIds, INITIAL_WINDOWS_DOC, type WindowsDoc } from "./ui/windowState";

// Each panel becomes its own chunk so first paint of the kiosk only ships
// the shell (header + dock + footer + the active panel). Big panels — xterm
// (~500 KB), marked + reading content, video player — only load when their
// tab is first tapped. We then KEEP them mounted via the `visited` set below
// so panel state (typing buffers, scrollback) survives tab switching.
const TerminalPanel = lazy(() =>
  import("./panels/TerminalPanel").then((m) => ({ default: m.TerminalPanel })),
);
const MessagesPanel = lazy(() =>
  import("./panels/MessagesPanel").then((m) => ({ default: m.MessagesPanel })),
);
const InboxPanel = lazy(() =>
  import("./panels/InboxPanel").then((m) => ({ default: m.InboxPanel })),
);
const ReadingPanel = lazy(() =>
  import("./panels/ReadingPanel").then((m) => ({ default: m.ReadingPanel })),
);
const TodoPanel = lazy(() =>
  import("./panels/TodoPanel").then((m) => ({ default: m.TodoPanel })),
);
const VideoPanel = lazy(() =>
  import("./panels/VideoPanel").then((m) => ({ default: m.VideoPanel })),
);
const GamesPanel = lazy(() =>
  import("./panels/GamesPanel").then((m) => ({ default: m.GamesPanel })),
);
const WikiPanel = lazy(() =>
  import("./panels/WikiPanel").then((m) => ({ default: m.WikiPanel })),
);
const WebPanel = lazy(() =>
  import("./panels/WebPanel").then((m) => ({ default: m.WebPanel })),
);
const BooksPanel = lazy(() =>
  import("./panels/BooksPanel").then((m) => ({ default: m.BooksPanel })),
);
const VoicePanel = lazy(() =>
  import("./panels/VoicePanel").then((m) => ({ default: m.VoicePanel })),
);
const NodesPanel = lazy(() =>
  import("./panels/NodesPanel").then((m) => ({ default: m.NodesPanel })),
);
const DesktopPanel = lazy(() =>
  import("./panels/DesktopPanel").then((m) => ({ default: m.DesktopPanel })),
);
const WorkbenchPanel = lazy(() =>
  import("./panels/WorkbenchPanel").then((m) => ({ default: m.WorkbenchPanel })),
);
const AppStorePanel = lazy(() =>
  import("./panels/AppStorePanel").then((m) => ({ default: m.AppStorePanel })),
);
const MusicPanel = lazy(() =>
  import("./panels/MusicPanel").then((m) => ({ default: m.MusicPanel })),
);

export function App() {
  const { t } = useTranslation("ui");
  const [bootMessage, setBootMessage] = useState(t("boot.waking"));
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Server-driven via /api/health: local Python returns true; hosted Vercel edge
  // returns false; missing endpoint fails closed (no gear, no web tab).
  const [settingsEnabled, setSettingsEnabled] = useState(false);
  const [webPanelEnabled, setWebPanelEnabled] = useState(false);
  const [nodesEnabled, setNodesEnabled] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [inboxEnabled, setInboxEnabled] = useState(false);
  const [windowDoc, updateWindows] = useSyncedDoc<WindowsDoc>("windows", INITIAL_WINDOWS_DOC);
  const [conversationDoc] = useConversationLog();
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(
        (d: {
          settings_enabled?: boolean;
          web_panel_enabled?: boolean;
          nodes_enabled?: boolean;
          nodes_ui_enabled?: boolean;
          sync_enabled?: boolean;
          inbox_enabled?: boolean;
        }) => {
          const nextNodesEnabled = d.nodes_ui_enabled ?? d.nodes_enabled ?? false;
          setSettingsEnabled(d.settings_enabled ?? false);
          setWebPanelEnabled(d.web_panel_enabled ?? false);
          setNodesEnabled(nextNodesEnabled);
          setSyncEnabled(d.sync_enabled ?? nextNodesEnabled);
          setInboxEnabled(d.inbox_enabled ?? false);
        },
      )
      .catch(() => {
        setSettingsEnabled(false);
        setWebPanelEnabled(false);
        setNodesEnabled(false);
        setSyncEnabled(false);
        setInboxEnabled(false);
      });
  }, []);

  useEffect(() => {
    if (!syncEnabled) return;
    // Kick off the Automerge sync WS once we know sync is permitted by
    // the server. Idempotent — repo.ts guards against double-connect.
    void import("./sync/repo").then((m) => m.startSync());
  }, [syncEnabled]);

  useEffect(() => {
    try {
      const legacy = typeof localStorage !== "undefined" && localStorage.getItem("hosaka.immersive") === "1";
      if (legacy && !windowDoc.chromeCollapsed) {
        updateWindows((doc) => {
          doc.chromeCollapsed = true;
        });
      }
    } catch {
      // ignore storage failures
    }
    // one-shot migration
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Apply font-size preference from localStorage immediately on mount.
  useEffect(() => {
    applyFontSize(loadUiConfig().fontSize);
    // Re-apply whenever the operator changes it via the settings drawer.
    const handler = () => applyFontSize(loadUiConfig().fontSize);
    window.addEventListener("hosaka:ui-changed", handler);
    return () => window.removeEventListener("hosaka:ui-changed", handler);
  }, []);

  const appFlags = useMemo(
    () => ({ inboxEnabled, webPanelEnabled, nodesEnabled }),
    [inboxEnabled, webPanelEnabled, nodesEnabled],
  );
  const enabledApps = useMemo(() => listEnabledApps(appFlags), [appFlags]);
  const enabledIds = useMemo(() => new Set(enabledApps.map((app) => app.id)), [enabledApps]);
  const launcherApps = useMemo(
    () => enabledApps.filter((app) => app.showInLauncher !== false),
    [enabledApps],
  );
  const openAppIds = useMemo(() => {
    const filtered = windowDoc.openAppIds.filter((appId) => enabledIds.has(appId));
    return dedupeAppIds(["home", ...filtered]);
  }, [enabledIds, windowDoc.openAppIds]);
  const activeAppId = useMemo(() => {
    if (enabledIds.has(windowDoc.activeAppId) && openAppIds.includes(windowDoc.activeAppId)) {
      return windowDoc.activeAppId;
    }
    return openAppIds[openAppIds.length - 1] ?? "home";
  }, [enabledIds, openAppIds, windowDoc.activeAppId]);

  const openApp = useCallback((appId: AppId) => {
    const definition = getAppDefinition(appId);
    if (!definition || !enabledIds.has(appId)) return;
    const now = Date.now();
    updateWindows((doc) => {
      doc.openAppIds = dedupeAppIds([...doc.openAppIds, appId]);
      doc.activeAppId = appId;
      doc.windows[appId] = {
        appId,
        background: doc.windows[appId]?.background ?? Boolean(definition.defaultBackground),
        lastOpenedAt: doc.windows[appId]?.lastOpenedAt ?? now,
        lastFocusedAt: now,
        openCount: (doc.windows[appId]?.openCount ?? 0) + 1,
        snapshot: doc.windows[appId]?.snapshot,
      };
    });
  }, [enabledIds, updateWindows]);

  const closeApp = useCallback((appId: AppId) => {
    const definition = getAppDefinition(appId);
    if (!definition || definition.closable === false) return;
    updateWindows((doc) => {
      doc.openAppIds = doc.openAppIds.filter((id) => id !== appId);
      if (doc.activeAppId === appId) {
        const remaining = dedupeAppIds(["home", ...doc.openAppIds]);
        doc.activeAppId = remaining[remaining.length - 1] ?? "home";
      }
    });
  }, [updateWindows]);

  const setActiveApp = useCallback((appId: AppId) => {
    if (!enabledIds.has(appId)) return;
    openApp(appId);
  }, [enabledIds, openApp]);

  const toggleChromeCollapsed = useCallback(() => {
    updateWindows((doc) => {
      doc.chromeCollapsed = !doc.chromeCollapsed;
    });
  }, [updateWindows]);

  const stageTerminalCommand = useCallback((command: string, autoSubmit = false) => {
    const trimmed = command.trim();
    if (!trimmed) return;
    openApp("terminal");
    window.dispatchEvent(
      new CustomEvent("hosaka:terminal-stage-command", {
        detail: { command: trimmed, autoSubmit },
      }),
    );
  }, [openApp]);

  useEffect(() => {
    const timer = setTimeout(() => setBootMessage(t("boot.steady")), 900);
    return () => clearTimeout(timer);
  }, [t]);

  useEffect(() => {
    const onSettings = () => setSettingsOpen(true);
    const onTab = (e: Event) => {
      const detail = (e as CustomEvent<string | { appId?: string; target?: string }>).detail;
      const target = typeof detail === "string"
        ? detail
        : detail?.appId ?? detail?.target ?? "";
      const appId = resolveAppId(target);
      if (appId) openApp(appId);
    };
    const onClose = (e: Event) => {
      const detail = (e as CustomEvent<string | { appId?: string }>).detail;
      const target = typeof detail === "string" ? detail : detail?.appId ?? "";
      const appId = resolveAppId(target);
      if (appId) closeApp(appId);
    };
    window.addEventListener("hosaka:open-settings", onSettings);
    window.addEventListener("hosaka:open-tab", onTab as EventListener);
    window.addEventListener("hosaka:open-app", onTab as EventListener);
    window.addEventListener("hosaka:close-app", onClose as EventListener);
    return () => {
      window.removeEventListener("hosaka:open-settings", onSettings);
      window.removeEventListener("hosaka:open-tab", onTab as EventListener);
      window.removeEventListener("hosaka:open-app", onTab as EventListener);
      window.removeEventListener("hosaka:close-app", onClose as EventListener);
    };
  }, [closeApp, openApp]);

  const renderApp = useCallback((appId: AppId) => {
    switch (appId) {
      case "home":
        return (
          <DesktopPanel
            mode="desktop"
            apps={enabledApps}
            openAppIds={openAppIds}
            activeAppId={activeAppId}
            conversation={conversationDoc.entries}
            onOpenApp={openApp}
            onCloseApp={closeApp}
            onStageCommand={stageTerminalCommand}
          />
        );
      case "tool_directory":
        return (
          <DesktopPanel
            mode="directory"
            apps={[...APP_REGISTRY]}
            openAppIds={openAppIds}
            activeAppId={activeAppId}
            conversation={conversationDoc.entries}
            onOpenApp={openApp}
            onCloseApp={closeApp}
            onStageCommand={stageTerminalCommand}
          />
        );
      case "workbench":
        return (
          <WorkbenchPanel
            apps={enabledApps}
            conversation={conversationDoc.entries}
            onOpenApp={openApp}
            onStageCommand={stageTerminalCommand}
          />
        );
      case "terminal":
        return <TerminalPanel active={activeAppId === "terminal"} />;
      case "inbox":
        return <InboxPanel />;
      case "messages":
        return <MessagesPanel />;
      case "reading":
        return <ReadingPanel active={activeAppId === "reading"} />;
      case "todo":
        return <TodoPanel />;
      case "video":
        return <VideoPanel active={activeAppId === "video"} />;
      case "games":
        return <GamesPanel active={activeAppId === "games"} />;
      case "wiki":
        return <WikiPanel active={activeAppId === "wiki"} />;
      case "web":
        return <WebPanel active={activeAppId === "web"} />;
      case "books":
        return <BooksPanel active={activeAppId === "books"} />;
      case "app_store":
        return <AppStorePanel />;
      case "music":
        return <MusicPanel />;
      case "voice":
        return <VoicePanel active={activeAppId === "voice"} />;
      case "nodes":
        return <NodesPanel />;
      default:
        return (
          <div className="desktop-panel desktop-panel--directory">
            <div className="panel-header">
              <h2><span className="panel-glyph">…</span> {appId}</h2>
              <p className="panel-sub">this surface is planned but not mounted yet.</p>
            </div>
          </div>
        );
    }
  }, [activeAppId, closeApp, conversationDoc.entries, enabledApps, openApp, openAppIds, stageTerminalCommand]);

  return (
    <div className={`hosaka-shell${windowDoc.chromeCollapsed ? " hosaka-shell--chrome-collapsed" : ""}`}>
      <header className="hosaka-topbar">
        <div className="hosaka-brand">
          <span className="hosaka-brand-logo">{t("brand")}</span>
          <span className="hosaka-brand-sub">{t("brandSub")}</span>
        </div>
        <div className="hosaka-topbar-right">
          <LangPicker />
          <SignalBadge label={bootMessage} />
          <PlantBadge />
          <ModeSwitch />
          <button
            type="button"
            className="icon-btn hosaka-chevron"
            aria-label={windowDoc.chromeCollapsed ? t("chrome.expand", "expand chrome") : t("chrome.collapse", "collapse chrome")}
            title={windowDoc.chromeCollapsed ? t("chrome.expand", "expand chrome") : t("chrome.collapse", "collapse chrome")}
            aria-pressed={windowDoc.chromeCollapsed}
            onClick={toggleChromeCollapsed}
          >
            {windowDoc.chromeCollapsed ? "⌄" : "⌃"}
          </button>
          {settingsEnabled && (
            <button
              className="icon-btn"
              aria-label={t("settings")}
              title={t("settings")}
              onClick={() => setSettingsOpen(true)}
            >
              ⚙
            </button>
          )}
        </div>
      </header>

      <nav className="hosaka-dock">
        <div className="hosaka-launchbar">
          <label className="hosaka-dock-picker">
            <span className="hosaka-dock-picker-label dim">{t("tabs.jump", "app")}</span>
            <select
              className="hosaka-panel-select"
              value={activeAppId}
              aria-label={t("tabs.jump", "app")}
              onChange={(e) => setActiveApp(e.target.value as AppId)}
            >
              {enabledApps.map((app) => (
                <option key={app.id} value={app.id}>
                  {app.glyph} {app.title}
                </option>
              ))}
            </select>
          </label>
          {launcherApps.map((app) => (
            <button
              key={app.id}
              type="button"
              className={`hosaka-dock-btn ${activeAppId === app.id ? "is-active" : ""}`}
              onClick={() => setActiveApp(app.id)}
            >
              <span className="hosaka-dock-glyph">{app.glyph}</span>
              <span className="hosaka-dock-label">{app.title}</span>
            </button>
          ))}
        </div>

        <div className="hosaka-window-strip" role="tablist" aria-label="open windows">
          {openAppIds.map((appId) => {
            const app = getAppDefinition(appId);
            if (!app) return null;
            return (
              <button
                key={appId}
                role="tab"
                aria-selected={activeAppId === appId}
                className={`hosaka-window-tab ${activeAppId === appId ? "is-active" : ""}`}
                onClick={() => setActiveApp(appId)}
              >
                <span className="hosaka-window-title">{app.glyph} {app.title}</span>
                {app.closable !== false && (
                  <span
                    className="hosaka-window-close"
                    role="button"
                    aria-label={`close ${app.title}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      closeApp(appId);
                    }}
                  >
                    ×
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </nav>

      <main className="hosaka-stage">
        <Suspense fallback={null}>
          {openAppIds.map((appId) => (
            <div key={appId} className="hosaka-panel" hidden={activeAppId !== appId}>
              {renderApp(appId)}
            </div>
          ))}
        </Suspense>
      </main>

      {settingsEnabled && (
        <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      )}

      <footer className="hosaka-footer">
        <span className="hosaka-footer-dim">{t("footer")} · {openAppIds.length} windows</span>
      </footer>

      <FloatingOrb voiceActive={activeAppId === "voice"} />
    </div>
  );
}
