import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useTranslation } from "./i18n";
import { PlantBadge } from "./components/PlantBadge";
import { SignalBadge } from "./components/SignalBadge";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { LangPicker } from "./components/LangPicker";
import { ModeSwitch } from "./components/ModeSwitch";
import { applyFontSize, loadUiConfig } from "./uiConfig";
import { FloatingOrb } from "./components/FloatingOrb";

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

export type PanelId =
  | "terminal"
  | "inbox"
  | "messages"
  | "reading"
  | "todo"
  | "video"
  | "games"
  | "wiki"
  | "web"
  | "books"
  | "voice"
  | "nodes";

export function App() {
  const { t } = useTranslation("ui");
  const [active, setActive] = useState<PanelId>("terminal");
  const [bootMessage, setBootMessage] = useState(t("boot.waking"));
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Server-driven via /api/health: local Python returns true; hosted Vercel edge
  // returns false; missing endpoint fails closed (no gear, no web tab).
  const [settingsEnabled, setSettingsEnabled] = useState(false);
  const [webPanelEnabled, setWebPanelEnabled] = useState(false);
  const [nodesEnabled, setNodesEnabled] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [inboxEnabled, setInboxEnabled] = useState(false);
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

  // Immersive mode: hide topbar/footer/dock-buttons and collapse the web
  // panel's hint line so the browsed page gets ~all of the viewport. Toggled
  // by the chevron in the dock. Persists so the kiosk re-boots into whichever
  // mode the operator left it in.
  const [immersive, setImmersive] = useState(
    () => typeof localStorage !== "undefined" && localStorage.getItem("hosaka.immersive") === "1",
  );
  useEffect(() => {
    try { localStorage.setItem("hosaka.immersive", immersive ? "1" : "0"); } catch {}
  }, [immersive]);

  // Apply font-size preference from localStorage immediately on mount.
  useEffect(() => {
    applyFontSize(loadUiConfig().fontSize);
    // Re-apply whenever the operator changes it via the settings drawer.
    const handler = () => applyFontSize(loadUiConfig().fontSize);
    window.addEventListener("hosaka:ui-changed", handler);
    return () => window.removeEventListener("hosaka:ui-changed", handler);
  }, []);

  // Track which panels the operator has actually visited so far. We only
  // render (and therefore only load the chunk for) panels they've tapped.
  // The terminal is in the set from the start because it's the default tab.
  const [visited, setVisited] = useState<Set<PanelId>>(() => new Set(["terminal"]));
  useEffect(() => {
    setVisited((s) => (s.has(active) ? s : new Set(s).add(active)));
  }, [active]);

  useEffect(() => {
    if (!webPanelEnabled && active === "web") setActive("terminal");
    if (!nodesEnabled && active === "nodes") setActive("terminal");
    if (!inboxEnabled && active === "inbox") setActive("terminal");
  }, [webPanelEnabled, nodesEnabled, inboxEnabled, active]);

  const panels = useMemo<{ id: PanelId; label: string; glyph: string }[]>(() => {
    const all: { id: PanelId; label: string; glyph: string }[] = [
      { id: "terminal", label: t("tabs.terminal"), glyph: "›_" },
      { id: "inbox", label: t("tabs.inbox", "inbox"), glyph: "☰" },
      { id: "voice", label: t("tabs.voice", "voice"), glyph: "◎" },
      { id: "reading", label: t("tabs.reading"), glyph: "❑" },
      { id: "todo", label: t("tabs.openLoops"), glyph: "▣" },
      { id: "video", label: t("tabs.video", "video"), glyph: "▶" },
      { id: "games", label: t("tabs.games", "games"), glyph: "◆" },
      { id: "wiki", label: t("tabs.wiki", "wiki"), glyph: "W" },
      { id: "web", label: t("tabs.web", "web"), glyph: "⌁" },
      { id: "books", label: t("tabs.books", "books"), glyph: "📖" },
      { id: "nodes", label: t("tabs.nodes", "nodes"), glyph: "◈" },
    ];
    return all.filter((p) => {
      if (p.id === "inbox" && !inboxEnabled) return false;
      if (p.id === "web" && !webPanelEnabled) return false;
      if (p.id === "nodes" && !nodesEnabled) return false;
      return true;
    });
  }, [t, inboxEnabled, webPanelEnabled, nodesEnabled]);

  useEffect(() => {
    const timer = setTimeout(() => setBootMessage(t("boot.steady")), 900);
    return () => clearTimeout(timer);
  }, [t]);

  useEffect(() => {
    const onSettings = () => setSettingsOpen(true);
    const onTab = (e: Event) => {
      const detail = (e as CustomEvent<PanelId>).detail;
      if (detail) setActive(detail);
    };
    window.addEventListener("hosaka:open-settings", onSettings);
    window.addEventListener("hosaka:open-tab", onTab as EventListener);
    return () => {
      window.removeEventListener("hosaka:open-settings", onSettings);
      window.removeEventListener("hosaka:open-tab", onTab as EventListener);
    };
  }, []);

  return (
    <div className={`hosaka-shell${immersive ? " hosaka-shell--immersive" : ""}`}>
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

      <nav className="hosaka-dock" role="tablist">
        <button
          type="button"
          className="hosaka-chevron"
          aria-label={immersive ? t("chrome.expand", "expand chrome") : t("chrome.collapse", "collapse chrome")}
          title={immersive ? t("chrome.expand", "expand chrome") : t("chrome.collapse", "collapse chrome")}
          aria-pressed={immersive}
          onClick={() => setImmersive((v) => !v)}
        >
          {immersive ? "⌄" : "⌃"}
        </button>
        <label className="hosaka-dock-picker">
          <span className="hosaka-dock-picker-label dim">{t("tabs.jump", "view")}</span>
          <select
            className="hosaka-panel-select"
            value={active}
            aria-label={t("tabs.jump", "view")}
            onChange={(e) => setActive(e.target.value as PanelId)}
          >
            {panels.map((p) => (
              <option key={p.id} value={p.id}>
                {p.glyph} {p.label}
              </option>
            ))}
          </select>
        </label>
        {panels.map((p) => (
          <button
            key={p.id}
            role="tab"
            aria-selected={active === p.id}
            className={`hosaka-dock-btn ${active === p.id ? "is-active" : ""}`}
            onClick={() => setActive(p.id)}
          >
            <span className="hosaka-dock-glyph">{p.glyph}</span>
            <span className="hosaka-dock-label">{p.label}</span>
          </button>
        ))}
      </nav>

      <main className="hosaka-stage">
        <Suspense fallback={null}>
          {visited.has("terminal") && (
            <div className="hosaka-panel" hidden={active !== "terminal"}>
              <TerminalPanel active={active === "terminal"} />
            </div>
          )}
          {inboxEnabled && visited.has("inbox") && (
            <div className="hosaka-panel" hidden={active !== "inbox"}>
              <InboxPanel />
            </div>
          )}
          {visited.has("messages") && (
            <div className="hosaka-panel" hidden={active !== "messages"}>
              <MessagesPanel />
            </div>
          )}
          {visited.has("reading") && (
            <div className="hosaka-panel" hidden={active !== "reading"}>
              <ReadingPanel active={active === "reading"} />
            </div>
          )}
          {visited.has("todo") && (
            <div className="hosaka-panel" hidden={active !== "todo"}>
              <TodoPanel />
            </div>
          )}
          {visited.has("video") && (
            <div className="hosaka-panel" hidden={active !== "video"}>
              <VideoPanel active={active === "video"} />
            </div>
          )}
          {visited.has("games") && (
            <div className="hosaka-panel" hidden={active !== "games"}>
              <GamesPanel active={active === "games"} />
            </div>
          )}
          {visited.has("wiki") && (
            <div className="hosaka-panel" hidden={active !== "wiki"}>
              <WikiPanel active={active === "wiki"} />
            </div>
          )}
          {webPanelEnabled && visited.has("web") && (
            <div className="hosaka-panel" hidden={active !== "web"}>
              <WebPanel active={active === "web"} />
            </div>
          )}
          {visited.has("books") && (
            <div className="hosaka-panel" hidden={active !== "books"}>
              <BooksPanel active={active === "books"} />
            </div>
          )}
          {visited.has("voice") && (
            <div className="hosaka-panel" hidden={active !== "voice"}>
              <VoicePanel active={active === "voice"} />
            </div>
          )}
          {nodesEnabled && visited.has("nodes") && (
            <div className="hosaka-panel" hidden={active !== "nodes"}>
              <NodesPanel />
            </div>
          )}
        </Suspense>
      </main>

      {settingsEnabled && (
        <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      )}

      <footer className="hosaka-footer">
        <span className="hosaka-footer-dim">{t("footer")}</span>
      </footer>

      <FloatingOrb voiceActive={active === "voice"} />
    </div>
  );
}
