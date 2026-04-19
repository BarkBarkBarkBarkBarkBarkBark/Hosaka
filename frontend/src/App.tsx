import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { TerminalPanel } from "./panels/TerminalPanel";
import { MessagesPanel } from "./panels/MessagesPanel";
import { ReadingPanel } from "./panels/ReadingPanel";
import { TodoPanel } from "./panels/TodoPanel";
import { VideoPanel } from "./panels/VideoPanel";
import { PlantBadge } from "./components/PlantBadge";
import { SignalBadge } from "./components/SignalBadge";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { LangPicker } from "./components/LangPicker";

export type PanelId = "terminal" | "messages" | "reading" | "todo" | "video";

const SHOW_SETTINGS = import.meta.env.VITE_SHOW_SETTINGS === "1";

export function App() {
  const { t } = useTranslation("ui");
  const [active, setActive] = useState<PanelId>("terminal");
  const [bootMessage, setBootMessage] = useState(t("boot.waking"));
  const [settingsOpen, setSettingsOpen] = useState(false);

  const panels: { id: PanelId; label: string; glyph: string }[] = [
    { id: "terminal", label: t("tabs.terminal"), glyph: "›_" },
    { id: "reading", label: t("tabs.reading"), glyph: "❑" },
    { id: "todo", label: t("tabs.openLoops"), glyph: "▣" },
    { id: "video", label: t("tabs.video", "video"), glyph: "▶" },
  ];

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
        <div className="hosaka-panel" hidden={active !== "terminal"}>
          <TerminalPanel active={active === "terminal"} />
        </div>
        <div className="hosaka-panel" hidden={active !== "messages"}>
          <MessagesPanel />
        </div>
        <div className="hosaka-panel" hidden={active !== "reading"}>
          <ReadingPanel active={active === "reading"} />
        </div>
        <div className="hosaka-panel" hidden={active !== "todo"}>
          <TodoPanel />
        </div>
        <div className="hosaka-panel" hidden={active !== "video"}>
          <VideoPanel active={active === "video"} />
        </div>
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
