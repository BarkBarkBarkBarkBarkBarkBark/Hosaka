import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useTranslation } from "./i18n";
import { PlantBadge } from "./components/PlantBadge";
import { SignalBadge } from "./components/SignalBadge";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { LangPicker } from "./components/LangPicker";
import { ModeSwitch } from "./components/ModeSwitch";

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

export type PanelId =
  | "terminal"
  | "messages"
  | "reading"
  | "todo"
  | "video"
  | "games"
  | "wiki"
  | "web";

const SHOW_SETTINGS = import.meta.env.VITE_SHOW_SETTINGS === "1";

export function App() {
  const { t } = useTranslation("ui");
  const [active, setActive] = useState<PanelId>("terminal");
  const [bootMessage, setBootMessage] = useState(t("boot.waking"));
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Track which panels the operator has actually visited so far. We only
  // render (and therefore only load the chunk for) panels they've tapped.
  // The terminal is in the set from the start because it's the default tab.
  const [visited, setVisited] = useState<Set<PanelId>>(() => new Set(["terminal"]));
  useEffect(() => {
    setVisited((s) => (s.has(active) ? s : new Set(s).add(active)));
  }, [active]);

  const panels = useMemo<{ id: PanelId; label: string; glyph: string }[]>(
    () => [
      { id: "terminal", label: t("tabs.terminal"), glyph: "›_" },
      { id: "reading", label: t("tabs.reading"), glyph: "❑" },
      { id: "todo", label: t("tabs.openLoops"), glyph: "▣" },
      { id: "video", label: t("tabs.video", "video"), glyph: "▶" },
      { id: "games", label: t("tabs.games", "games"), glyph: "◆" },
      { id: "wiki",  label: t("tabs.wiki",  "wiki"),  glyph: "W" },
      { id: "web",   label: t("tabs.web",   "web"),   glyph: "⌁" },
    ],
    [t],
  );

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
    <div className="hosaka-shell">
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
          {SHOW_SETTINGS && (
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
          {visited.has("web") && (
            <div className="hosaka-panel" hidden={active !== "web"}>
              <WebPanel active={active === "web"} />
            </div>
          )}
        </Suspense>
      </main>

      {SHOW_SETTINGS && (
        <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      )}

      <footer className="hosaka-footer">
        <span className="hosaka-footer-dim">{t("footer")}</span>
      </footer>
    </div>
  );
}
