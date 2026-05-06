import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "./i18n";
import { PlantBadge } from "./components/PlantBadge";
import { SignalBadge } from "./components/SignalBadge";
import { LangPicker } from "./components/LangPicker";
import { ModeSwitch } from "./components/ModeSwitch";
import { HosakaMenu } from "./components/HosakaMenu";
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
import { dedupeAppIds, INITIAL_WINDOWS_DOC, type WindowEntry, type WindowsDoc } from "./ui/windowState";
import { OverlayStack } from "./components/OverlayStack";

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
const DocsPanel = lazy(() =>
  import("./panels/DocsPanel").then((m) => ({ default: m.DocsPanel })),
);
const DiagnosticsPanel = lazy(() =>
  import("./panels/DiagnosticsPanel").then((m) => ({ default: m.DiagnosticsPanel })),
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
const HelpPanel = lazy(() =>
  import("./panels/HelpPanel").then((m) => ({ default: m.HelpPanel })),
);
const DeviceCheckPanel = lazy(() =>
  import("./panels/DeviceCheckPanel").then((m) => ({ default: m.DeviceCheckPanel })),
);
const ExternalAppPanel = lazy(() =>
  import("./panels/ExternalAppPanel").then((m) => ({ default: m.ExternalAppPanel })),
);
import { CmdLine } from "./components/CmdLine";
import { HintLayer } from "./components/HintLayer";
import { useShortcuts } from "./ui/useShortcuts";

export function App() {
  const { t } = useTranslation("ui");
  useShortcuts();
  const [bootMessage, setBootMessage] = useState(t("boot.waking"));
  const [webPanelEnabled, setWebPanelEnabled] = useState(false);
  const [nodesEnabled, setNodesEnabled] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [inboxEnabled, setInboxEnabled] = useState(false);
  const [windowDoc, updateWindows] = useSyncedDoc<WindowsDoc>("windows", INITIAL_WINDOWS_DOC);
  const [conversationDoc] = useConversationLog();
  const [activeOverride, setActiveOverride] = useState<AppId | null>(null);
  const [openOverride, setOpenOverride] = useState<AppId[] | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [docToast, setDocToast] = useState<{ path: string; at: number } | null>(null);
  const [hostPlatform, setHostPlatform] = useState<string | null>(null);
  const [exposeOpen, setExposeOpen] = useState(false);
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(
        (d: {
          web_panel_enabled?: boolean;
          nodes_enabled?: boolean;
          nodes_ui_enabled?: boolean;
          sync_enabled?: boolean;
          inbox_enabled?: boolean;
        }) => {
          const nextNodesEnabled = d.nodes_ui_enabled ?? d.nodes_enabled ?? false;
          setWebPanelEnabled(d.web_panel_enabled ?? false);
          setNodesEnabled(nextNodesEnabled);
          setSyncEnabled(d.sync_enabled ?? nextNodesEnabled);
          setInboxEnabled(d.inbox_enabled ?? false);
        },
      )
      .catch(() => {
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

  // Platform probe — resolves Linux-only apps in the registry. Falls back
  // to navigator.platform on failure so non-Linux dev machines still hide
  // the flatpak apps from the launcher.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/apps/capabilities")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { platform?: string } | null) => {
        if (cancelled) return;
        const p = d?.platform ?? (typeof navigator !== "undefined" ? navigator.platform : null);
        setHostPlatform(p ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setHostPlatform(typeof navigator !== "undefined" ? navigator.platform : null);
      });
    return () => { cancelled = true; };
  }, []);

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
  const enabledApps = useMemo(() => listEnabledApps(appFlags, hostPlatform), [appFlags, hostPlatform]);
  const enabledIds = useMemo(() => new Set(enabledApps.map((app) => app.id)), [enabledApps]);
  const launcherApps = useMemo(
    () => enabledApps.filter((app) => app.showInLauncher !== false),
    [enabledApps],
  );
  const syncedOpenAppIds = useMemo(() => {
    const filtered = windowDoc.openAppIds.filter((appId) => enabledIds.has(appId));
    return dedupeAppIds(["terminal", ...filtered]);
  }, [enabledIds, windowDoc.openAppIds]);
  const openAppIds = useMemo(() => {
    const source = openOverride ?? syncedOpenAppIds;
    return dedupeAppIds(["terminal", ...source.filter((appId) => enabledIds.has(appId))]);
  }, [enabledIds, openOverride, syncedOpenAppIds]);
  const activeAppId = useMemo(() => {
    if (activeOverride && enabledIds.has(activeOverride) && openAppIds.includes(activeOverride)) {
      return activeOverride;
    }
    if (enabledIds.has(windowDoc.activeAppId) && openAppIds.includes(windowDoc.activeAppId)) {
      return windowDoc.activeAppId;
    }
    return openAppIds[openAppIds.length - 1] ?? "terminal";
  }, [activeOverride, enabledIds, openAppIds, windowDoc.activeAppId]);

  // #region agent log (DEV only — guard with import.meta.env.DEV so esbuild
  // dead-code-eliminates the body in production. On the Pi the layout
  // sweep alone burned a non-trivial amount of CPU because querySelector +
  // getComputedStyle on every render is not free.)
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const dbg = (window as unknown as { __hosakaDbg?: (loc: string, msg: string, data?: Record<string, unknown>) => void }).__hosakaDbg;
    dbg?.("App.tsx:render", "active state computed", {
      activeAppId,
      docActiveAppId: windowDoc.activeAppId,
      docChromeCollapsed: windowDoc.chromeCollapsed,
      docOpenAppIds: windowDoc.openAppIds,
      openAppIds,
      activeOverride,
      openOverride,
      enabledCount: enabledIds.size,
    });
  }, [activeAppId, windowDoc.activeAppId, windowDoc.chromeCollapsed, windowDoc.openAppIds, openAppIds, activeOverride, openOverride, enabledIds]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const dbg = (window as unknown as { __hosakaDbg?: (loc: string, msg: string, data?: Record<string, unknown>) => void }).__hosakaDbg;
    const tick = () => {
      const stage = document.querySelector(".hosaka-stage") as HTMLElement | null;
      const panel = document.querySelector(".hosaka-panel:not([hidden])") as HTMLElement | null;
      const termWrap = document.querySelector(".terminal-wrap") as HTMLElement | null;
      const termHost = document.querySelector(".terminal-host") as HTMLElement | null;
      const xterm = document.querySelector(".xterm") as HTMLElement | null;
      dbg?.("App.tsx:layout", "post-paint dimensions", {
        viewport: { w: window.innerWidth, h: window.innerHeight },
        stage: stage ? { w: stage.offsetWidth, h: stage.offsetHeight, display: getComputedStyle(stage).display } : null,
        panel: panel ? { w: panel.offsetWidth, h: panel.offsetHeight, hidden: panel.hidden, classes: panel.className.slice(0, 60) } : null,
        termWrap: termWrap ? { w: termWrap.offsetWidth, h: termWrap.offsetHeight } : null,
        termHost: termHost ? { w: termHost.offsetWidth, h: termHost.offsetHeight, children: termHost.childElementCount } : null,
        xterm: xterm ? { w: xterm.offsetWidth, h: xterm.offsetHeight } : null,
        rootChildren: document.getElementById("root")?.childElementCount ?? 0,
      });
    };
    const t1 = setTimeout(tick, 500);
    const t2 = setTimeout(tick, 2000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);
  // #endregion

  const openApp = useCallback((appId: AppId) => {
    const definition = getAppDefinition(appId);
    if (!definition || !enabledIds.has(appId)) return;
    setOpenOverride((prev) => dedupeAppIds([...(prev ?? openAppIds), appId]));
    setActiveOverride(appId);
    const now = Date.now();
    updateWindows((doc) => {
      const openIds: AppId[] = Array.isArray(doc.openAppIds) ? doc.openAppIds : ["terminal"];
      doc.openAppIds = dedupeAppIds([...openIds, appId]);
      doc.activeAppId = appId;
      if (!doc.windows || typeof doc.windows !== "object") doc.windows = {};
      const prev = doc.windows[appId];
      // Automerge rejects assignment of `undefined` (see runtime evidence:
      // RangeError: Cannot assign undefined value at /windows/<id>/snapshot).
      // Build the new entry with snapshot only when we have one to carry over.
      const next: WindowEntry = {
        appId,
        background: prev?.background ?? Boolean(definition.defaultBackground),
        lastOpenedAt: prev?.lastOpenedAt ?? now,
        lastFocusedAt: now,
        openCount: (prev?.openCount ?? 0) + 1,
      };
      if (prev?.snapshot !== undefined) next.snapshot = prev.snapshot;
      doc.windows[appId] = next;
    });
  }, [enabledIds, openAppIds, updateWindows]);

  const closeApp = useCallback((appId: AppId) => {
    const definition = getAppDefinition(appId);
    if (!definition || definition.closable === false) return;
    const nextOpen = openAppIds.filter((id) => id !== appId);
    setOpenOverride(nextOpen);
    if (activeOverride === appId) {
      setActiveOverride(nextOpen[nextOpen.length - 1] ?? "terminal");
    }
    updateWindows((doc) => {
      const openIds: AppId[] = Array.isArray(doc.openAppIds) ? doc.openAppIds : ["terminal"];
      doc.openAppIds = openIds.filter((id) => id !== appId);
      if (doc.activeAppId === appId) {
        const remaining = dedupeAppIds(["terminal", ...doc.openAppIds]);
        doc.activeAppId = remaining[remaining.length - 1] ?? "terminal";
        setActiveOverride(doc.activeAppId);
      }
    });
  }, [activeOverride, openAppIds, updateWindows]);

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
    const onToggleMenu = () => setNavOpen((v) => !v);
    const onToggleChrome = () => {
      updateWindows((doc) => { doc.chromeCollapsed = !doc.chromeCollapsed; });
    };
    const onFocusTerminal = () => {
      openApp("terminal");
      window.dispatchEvent(new CustomEvent("hosaka:overlay-close-all", { detail: { keepPinned: true } }));
    };
    // Global Esc panic: if Esc reaches the window without anything
    // claiming it (no input focused), close the menu + all overlays so a
    // user is never trapped behind a transient surface.
    const onEscPanic = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || t?.isContentEditable) return;
      setNavOpen(false);
      window.dispatchEvent(new CustomEvent("hosaka:overlay-close-all", { detail: { keepPinned: false } }));
    };
    window.addEventListener("hosaka:open-tab", onTab as EventListener);
    window.addEventListener("hosaka:open-app", onTab as EventListener);
    window.addEventListener("hosaka:close-app", onClose as EventListener);
    window.addEventListener("hosaka:toggle-menu", onToggleMenu);
    window.addEventListener("hosaka:toggle-chrome", onToggleChrome);
    window.addEventListener("hosaka:focus-terminal", onFocusTerminal);
    window.addEventListener("keydown", onEscPanic);
    const onExpose = () => setExposeOpen((v) => !v);
    window.addEventListener("hosaka:expose-windows", onExpose);
    return () => {
      window.removeEventListener("hosaka:open-tab", onTab as EventListener);
      window.removeEventListener("hosaka:open-app", onTab as EventListener);
      window.removeEventListener("hosaka:close-app", onClose as EventListener);
      window.removeEventListener("hosaka:toggle-menu", onToggleMenu);
      window.removeEventListener("hosaka:toggle-chrome", onToggleChrome);
      window.removeEventListener("hosaka:focus-terminal", onFocusTerminal);
      window.removeEventListener("keydown", onEscPanic);
      window.removeEventListener("hosaka:expose-windows", onExpose);
    };
  }, [closeApp, openApp, updateWindows]);

  // Doc-write toast: agent saved a markdown doc — surface a non-hijacking
  // hint with tap-to-open. Fires from realtimeClient and DocsPanel saves.
  useEffect(() => {
    const onDoc = (e: Event) => {
      const detail = (e as CustomEvent<{ path?: string }>).detail;
      const path = detail?.path?.toString() ?? "";
      if (!path) return;
      setDocToast({ path, at: Date.now() });
    };
    window.addEventListener("hosaka:doc-written", onDoc as EventListener);
    return () => window.removeEventListener("hosaka:doc-written", onDoc as EventListener);
  }, []);

  useEffect(() => {
    if (!docToast) return;
    const t = window.setTimeout(() => setDocToast(null), 6000);
    return () => window.clearTimeout(t);
  }, [docToast]);

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
            apps={APP_REGISTRY}
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
        return <InboxPanel active={activeAppId === "inbox"} />;
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
      case "docs":
        return <DocsPanel active={activeAppId === "docs"} />;
      case "diagnostics":
        return <DiagnosticsPanel active={activeAppId === "diagnostics"} />;
      case "app_store":
        return <AppStorePanel />;
      case "music":
        return <MusicPanel />;
      case "voice":
        return <VoicePanel active={activeAppId === "voice"} />;
      case "nodes":
        return <NodesPanel active={activeAppId === "nodes"} />;
      case "help":
        return <HelpPanel />;
      case "device_mic":
        return <DeviceCheckPanel kind="mic" onClose={() => closeApp("device_mic")} />;
      case "device_cam":
        return <DeviceCheckPanel kind="cam" onClose={() => closeApp("device_cam")} />;
      case "device_spk":
        return <DeviceCheckPanel kind="spk" onClose={() => closeApp("device_spk")} />;
      case "spotify":
      case "discord":
      case "foliate":
      case "vscode":
      case "firefox":
      case "telegram":
      case "betterbird":
      case "alienarena":
      case "slack":
      case "steam":
        return <ExternalAppPanel appId={appId} onClose={closeApp} />;
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

  // Stage-mode hint: panels that benefit from full-bleed (orb / terminal /
  // video / games / web) get an immersive class so CSS can collapse padding
  // and let the central surface dominate. Aesthetic only — no app logic.
  const immersiveApps = new Set<AppId>(["voice", "terminal", "video", "games", "web", "books", "reading", "docs", "diagnostics"]);
  const stageMode = immersiveApps.has(activeAppId) ? "immersive" : "chrome";

  return (
    <div
      className={`hosaka-shell hosaka-shell--stage-${stageMode}${windowDoc.chromeCollapsed ? " hosaka-shell--chrome-collapsed" : ""}`}
    >
      <header className="hosaka-topbar">
        <div className="hosaka-brand">
          <button
            type="button"
            className="hosaka-menu-trigger"
            aria-label="open menu"
            aria-expanded={navOpen}
            title="menu — apps · wifi · volume · appearance (Ctrl+M)"
            onClick={() => setNavOpen((v) => !v)}
          >☰</button>
          <span className="hosaka-brand-logo">{t("brand")}</span>
          <span className="hosaka-brand-sub">{t("brandSub")}</span>
        </div>
        <div className="hosaka-quickbar" role="toolbar" aria-label="quick actions">
          <button
            type="button"
            className={`icon-btn hosaka-quick-btn ${activeAppId === "terminal" ? "is-active" : ""}`}
            aria-label="focus terminal"
            title="terminal (Ctrl+T)"
            onClick={() => {
              setActiveApp("terminal");
              window.dispatchEvent(new CustomEvent("hosaka:overlay-close-all", { detail: { keepPinned: true } }));
            }}
          >›_</button>
          <button
            type="button"
            className="icon-btn hosaka-quick-btn"
            aria-label="open voice orb"
            title="orb (Ctrl+O)"
            onClick={() => setActiveApp("voice")}
          >◎</button>
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
        </div>
      </header>

      <HosakaMenu
        open={navOpen}
        onClose={() => setNavOpen(false)}
        apps={enabledApps}
        launcherApps={launcherApps}
        openAppIds={openAppIds}
        activeAppId={activeAppId}
        onSetActive={setActiveApp}
        onCloseApp={closeApp}
      />

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
          {openAppIds.map((appId) => {
            const isActive = activeAppId === appId;
            const keepMeasurableWhileInactive = appId === "terminal";
            return (
              <div
                key={appId}
                className={`hosaka-panel ${isActive ? "is-active" : "is-inactive"}`}
                hidden={!keepMeasurableWhileInactive && !isActive}
              >
                {renderApp(appId)}
              </div>
            );
          })}
        </Suspense>
      </main>

      <CmdLine />

      <footer className="hosaka-footer">
        <span className="hosaka-footer-dim">{t("footer")} · {openAppIds.length} windows</span>
      </footer>

      <FloatingOrb voiceActive={activeAppId === "voice"} />

      <OverlayStack />
      <HintLayer />

      {exposeOpen && (
        <div
          className="window-expose"
          role="dialog"
          aria-label="open windows"
          aria-modal="true"
          onClick={(e) => { if (e.target === e.currentTarget) setExposeOpen(false); }}
          onKeyDown={(e) => { if (e.key === "Escape") setExposeOpen(false); }}
          tabIndex={-1}
          ref={(el) => el?.focus()}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            backdropFilter: "blur(6px)",
            zIndex: 220,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "3rem",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
              gap: "1rem",
              maxWidth: "min(1200px, 100%)",
              maxHeight: "100%",
              overflow: "auto",
            }}
          >
            {openAppIds.map((id) => {
              const app = getAppDefinition(id);
              if (!app) return null;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => { setActiveApp(id); setExposeOpen(false); }}
                  style={{
                    background: id === activeAppId ? "rgba(120,160,255,0.18)" : "rgba(255,255,255,0.05)",
                    border: id === activeAppId ? "1px solid rgba(120,160,255,0.6)" : "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 8,
                    padding: "1.25rem 1rem",
                    color: "inherit",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "0.5rem",
                    minHeight: 120,
                  }}
                >
                  <span style={{ fontSize: "2rem" }}>{app.glyph}</span>
                  <span>{app.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      {docToast && (
        <div className="doc-toast" role="status" aria-live="polite">
          <span className="doc-toast-glyph">✎</span>
          <span className="doc-toast-text">saved <strong>{docToast.path}</strong></span>
          <button
            type="button"
            className="doc-toast-open"
            onClick={() => { openApp("docs"); setDocToast(null); }}
          >open</button>
          <button
            type="button"
            className="doc-toast-x"
            aria-label="dismiss"
            onClick={() => setDocToast(null)}
          >✕</button>
        </div>
      )}
    </div>
  );
}
