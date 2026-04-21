import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "../i18n";
import {
  getBrowserMode,
  INTERNAL_PANEL_PAGES,
  launchExternal,
  openUrl,
  type BrowserOpenResult,
  type InternalPage,
} from "./browserAdapter";

type Preset = {
  id: string;
  labelKey: string;
  url: string;
};

const PRESETS: Preset[] = [
  { id: "home", labelKey: "web.presetHome", url: "hosaka://home" },
  { id: "cyberspace", labelKey: "web.presetCyberspace", url: "https://cyberspace.online" },
  { id: "wiki", labelKey: "web.presetWiki", url: "https://en.wikipedia.org/wiki/Special:Random" },
  { id: "hn", labelKey: "web.presetHn", url: "https://news.ycombinator.com" },
  { id: "gh", labelKey: "web.presetGh", url: "https://github.com" },
  { id: "archive", labelKey: "web.presetArchive", url: "https://archive.org" },
  { id: "reddit", labelKey: "web.presetReddit", url: "https://old.reddit.com" },
  { id: "yt", labelKey: "web.presetYt", url: "https://m.youtube.com" },
  { id: "tiktok", labelKey: "web.presetTiktok", url: "https://www.tiktok.com" },
  { id: "ig", labelKey: "web.presetIg", url: "https://www.instagram.com" },
  { id: "discord", labelKey: "web.presetDiscord", url: "https://discord.com/app" },
  { id: "twitch", labelKey: "web.presetTwitch", url: "https://www.twitch.tv" },
  { id: "reddit_new", labelKey: "web.presetRedditNew", url: "https://www.reddit.com" },
  { id: "mastodon", labelKey: "web.presetMastodon", url: "https://mastodon.social/explore" },
  { id: "lobsters", labelKey: "web.presetLobsters", url: "https://lobste.rs" },
];

type BrowserEntry = { input: string; result: BrowserOpenResult };
type Props = { active: boolean };

export function WebPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const [presetId, setPresetId] = useState("home");
  const [urlInput, setUrlInput] = useState("hosaka://home");
  const [history, setHistory] = useState<BrowserEntry[]>([
    { input: "hosaka://home", result: { kind: "internal", url: "hosaka://home", page: "home" } },
  ]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState(getBrowserMode());

  const current = history[historyIndex] ?? history[0];
  const canBack = historyIndex > 0;
  const canForward = historyIndex < history.length - 1;

  const navigate = useCallback(async (input: string, push = true) => {
    setLoading(true);
    const result = await openUrl(input);
    setMode(getBrowserMode());
    setLoading(false);
    setUrlInput(result.kind === "unsupported" ? input : result.url);

    if (!push) {
      // Reload replaces the current history entry instead of adding a new one.
      setHistory((rows) => rows.map((row, idx) => (idx === historyIndex ? { input, result } : row)));
      return;
    }

    setHistory((rows) => {
      // Normal navigation drops forward history and appends a new current entry.
      const next = rows.slice(0, historyIndex + 1);
      next.push({ input, result });
      setHistoryIndex(next.length - 1);
      return next;
    });
  }, [historyIndex]);

  const onGo = () => {
    void navigate(urlInput, true);
  };

  const onPresetChange = useCallback((id: string) => {
    setPresetId(id);
    const p = PRESETS.find((x) => x.id === id);
    if (!p) return;
    setUrlInput(p.url);
    void navigate(p.url, true);
  }, [navigate]);

  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      if (id) onPresetChange(id);
    };
    const openHandler = (e: Event) => {
      const input = (e as CustomEvent<string>).detail;
      if (!input) return;
      setUrlInput(input);
      setPresetId("home");
      void navigate(input, true);
    };
    window.addEventListener("hosaka:web-preset", handler as EventListener);
    window.addEventListener("hosaka:web-open", openHandler as EventListener);
    return () => {
      window.removeEventListener("hosaka:web-preset", handler as EventListener);
      window.removeEventListener("hosaka:web-open", openHandler as EventListener);
    };
  }, [navigate, onPresetChange]);

  if (!active) return null;

  const result = current?.result;
  const internalResult = result?.kind === "internal" ? result : null;
  const isExternal = result?.kind === "external-browser";
  const isBlocked = result?.kind === "blocked";
  const isUnsupported = result?.kind === "unsupported";

  const onBack = () => {
    if (!canBack) return;
    const idx = historyIndex - 1;
    setHistoryIndex(idx);
    setUrlInput(history[idx]?.input ?? "");
  };

  const onForward = () => {
    if (!canForward) return;
    const idx = historyIndex + 1;
    setHistoryIndex(idx);
    setUrlInput(history[idx]?.input ?? "");
  };

  const onReload = () => {
    if (!current) return;
    void navigate(current.input, false);
  };

  const internalJump = (target: string) => {
    setPresetId("home");
    setUrlInput(target);
    void navigate(target, true);
  };

  return (
    <div className="web-panel">
      <div className="web-social-bar">
        {PRESETS.filter((p) => ["reddit", "tiktok", "discord", "yt", "twitch"].includes(p.id)).map((p) => (
          <button
            key={p.id}
            type="button"
            className="btn btn-ghost web-social-btn"
            onClick={() => onPresetChange(p.id)}
            title={t(p.labelKey, p.id)}
          >
            {t(p.labelKey, p.id)}
          </button>
        ))}
      </div>
      <div className="web-toolbar">
        <div className="web-nav-row">
          <button type="button" className="btn btn-ghost web-nav-btn" onClick={onBack} disabled={!canBack}>
            {t("web.back", "←")}
          </button>
          <button type="button" className="btn btn-ghost web-nav-btn" onClick={onForward} disabled={!canForward}>
            {t("web.forward", "→")}
          </button>
          <button type="button" className="btn btn-ghost web-nav-btn" onClick={onReload} disabled={loading}>
            {t("web.reload", "↻")}
          </button>
          <span className="web-mode-pill">{mode}</span>
        </div>
        <label className="web-label">
          <span className="dim">{t("web.presetLabel", "app")}</span>
          <select
            className="web-select"
            value={presetId}
            onChange={(e) => onPresetChange(e.target.value)}
          >
            {PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {t(p.labelKey, p.id)}
              </option>
            ))}
          </select>
        </label>
        <div className="web-url-row">
          <input
            type="text"
            className="web-url-input"
            spellCheck={false}
            placeholder={t("web.urlPlaceholder", "https://…")}
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onGo()}
          />
          <button type="button" className="btn btn-primary web-go" onClick={onGo}>
            {t("web.go", "go")}
          </button>
          {result && result.kind !== "unsupported" && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void launchExternal(result.url)}
              disabled={result.kind === "internal"}
            >
              {t("web.openTab", "↗ tab")}
            </button>
          )}
        </div>
      </div>
      <p className="web-hint dim small">
        {t("web.hint", "external pages use your browser adapter (tab/system/native). hosaka:// and panel routes stay inside this panel.")}
      </p>
      {isExternal && (
        <p className="web-external-note">
          {t("web.openedExternal", "opened externally:")} <code>{result.url}</code>
        </p>
      )}
      <div className="web-frame-wrap">
        {loading && <div className="web-empty">{t("web.loading", "loading…")}</div>}
        {!loading && isUnsupported && (
          <div className="web-empty">
            <div className="web-state">
              <h3>{t("web.unsupportedTitle", "unsupported address")}</h3>
              <p>{result.reason}</p>
            </div>
          </div>
        )}
        {!loading && isBlocked && (
          <div className="web-empty">
            <div className="web-state">
              <h3>{t("web.blockedTitle", "cannot render in-panel")}</h3>
              <p>{result.reason}</p>
              <p>{t("web.blockedHint", "this target must open through external/native browser mode.")}</p>
              <button type="button" className="btn btn-primary" onClick={() => void launchExternal(result.url)}>
                {t("web.openExternal", "open externally")}
              </button>
            </div>
          </div>
        )}
        {!loading && !isBlocked && !isUnsupported && (
          <InternalBrowserPage page={internalResult?.page ?? "home"} onOpen={internalJump} />
        )}
      </div>
    </div>
  );
}

function InternalBrowserPage({
  page,
  onOpen,
}: {
  page: InternalPage;
  onOpen: (target: string) => void;
}) {
  const { t } = useTranslation("ui");
  const entries = INTERNAL_PANEL_PAGES.filter((id) => id !== "web");

  if (page !== "home") {
    return (
      <div className="web-empty">
        <div className="web-state">
          <h3>{t("web.internalPageTitle", "hosaka internal page")}</h3>
          <p>
            <code>hosaka://panel/{page}</code>
          </p>
          <p>{t("web.internalPageHint", "this is internal app content. open the panel directly when needed.")}</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => window.dispatchEvent(new CustomEvent("hosaka:open-tab", { detail: page }))}
          >
            {t("web.openPanel", "open panel")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="web-empty">
      <div className="web-state">
        <h3>{t("web.homeTitle", "hosaka browser surface")}</h3>
        <p>{t("web.homeBody", "internal targets render here. external URLs launch through the active browser adapter.")}</p>
        <div className="web-internal-grid">
          {entries.map((id) => (
            <button
              key={id}
              type="button"
              className="btn btn-ghost web-internal-btn"
              onClick={() => onOpen(`hosaka://panel/${id}`)}
            >
              hosaka://panel/{id}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
