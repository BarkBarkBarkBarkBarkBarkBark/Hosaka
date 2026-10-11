/**
 * WebPanel — mini-browser surface with preset "apps".
 *
 * Render strategy is decided by the runtime environment, not by hardcoded
 * preset mode flags:
 *
 *   - Electron kiosk host (preload injects window.hosakaBrowserAdapter with
 *     mode: "native-webview")  → mount <webview>. No X-Frame-Options grief.
 *   - Plain browser / Vercel / a tab open on a laptop               → mount
 *     <iframe>, and show a "site blocks embedding?" disclosure; users can
 *     escape to a new tab with the ↗ button.
 *
 * The same bundle loads in both. The only branch is on `getBrowserMode()`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "../i18n";
import { getBrowserMode } from "./browserAdapter";
// electronWebview.d.ts is an ambient .d.ts — TS picks it up from tsconfig's
// include glob, no runtime import needed (and rollup can't resolve .d.ts).

// ── Tab model ────────────────────────────────────────────────────────────
// The web panel is now a tabbed mini-browser. We render only the *active*
// tab's <webview>/<iframe> so the Pi isn't decoding N pages in the
// background; inactive tabs are remembered as URL state and re-mount when
// selected. A dropdown switcher is the primary navigation (no horizontal
// strip — saves vertical real estate, plays well with the kiosk topbar).

type Tab = {
  id: string;
  url: string;          // the currently-loaded URL (drives <webview src>)
  urlInput: string;     // the address-bar value, may differ until "go"
  presetId: string;     // last preset selected for this tab
  title: string;        // best-effort, derived from URL host
};

type Preset = {
  id: string;
  labelKey: string;
  url: string;
};

const PRESETS: Preset[] = [
  { id: "cyberspace",labelKey: "web.presetCyberspace",url: "https://cyberspace.online" },
  { id: "custom",    labelKey: "web.presetCustom",    url: "" },
  { id: "wiki",      labelKey: "web.presetWiki",      url: "https://en.wikipedia.org/wiki/Special:Random" },
  { id: "hn",        labelKey: "web.presetHn",        url: "https://news.ycombinator.com" },
  { id: "gh",        labelKey: "web.presetGh",        url: "https://github.com" },
  { id: "archive",   labelKey: "web.presetArchive",   url: "https://archive.org" },
  { id: "reddit",    labelKey: "web.presetReddit",    url: "https://old.reddit.com" },
  { id: "yt",        labelKey: "web.presetYt",        url: "https://m.youtube.com" },
  { id: "tiktok",    labelKey: "web.presetTiktok",    url: "https://www.tiktok.com" },
  { id: "ig",        labelKey: "web.presetIg",        url: "https://www.instagram.com" },
  { id: "discord",   labelKey: "web.presetDiscord",   url: "https://discord.com/app" },
  { id: "twitch",    labelKey: "web.presetTwitch",    url: "https://www.twitch.tv" },
  { id: "reddit_new",labelKey: "web.presetRedditNew", url: "https://www.reddit.com" },
  { id: "mastodon",  labelKey: "web.presetMastodon",  url: "https://mastodon.social/explore" },
  { id: "lobsters",  labelKey: "web.presetLobsters",  url: "https://lobste.rs" },
];

function normalizeUrl(raw: string): string | null {
  const t = raw.trim();
  if (!t) return null;
  if (/^https?:\/\//i.test(t)) {
    try {
      const u = new URL(t);
      if (u.protocol !== "http:" && u.protocol !== "https:") return null;
      return u.href;
    } catch {
      return null;
    }
  }
  try {
    return new URL(`https://${t}`).href;
  } catch {
    return null;
  }
}

function titleFromUrl(url: string, fallback = "new tab"): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return fallback;
  }
}

let tabSeq = 0;
const newTabId = () => `tab-${Date.now().toString(36)}-${(tabSeq += 1).toString(36)}`;

function makeTab(url: string, presetId = "custom"): Tab {
  return {
    id: newTabId(),
    url,
    urlInput: url,
    presetId,
    title: titleFromUrl(url),
  };
}

type Props = { active: boolean };

export function WebPanel({ active }: Props) {
  const { t } = useTranslation("ui");

  // cyberspace.online is the canonical "front door" — the first tab seeds
  // there. Operators can always pick a preset, type a URL, or open a new tab.
  const [tabs, setTabs] = useState<Tab[]>(() => [
    makeTab("https://cyberspace.online", "cyberspace"),
  ]);
  const [activeId, setActiveId] = useState<string>(() => tabs[0]?.id ?? "");

  const active_ = useMemo(
    () => tabs.find((tab) => tab.id === activeId) ?? tabs[0],
    [tabs, activeId],
  );

  // We only evaluate once per mount — the kiosk host can't hot-swap the
  // preload bridge in. Plain browsers never get it. Either way the value
  // is stable for the life of the session.
  const [mode] = useState(() => getBrowserMode());
  const useWebview = mode === "native-webview";

  const updateActive = useCallback(
    (patch: Partial<Tab>) => {
      setTabs((prev) =>
        prev.map((tab) => (tab.id === activeId ? { ...tab, ...patch } : tab)),
      );
    },
    [activeId],
  );

  const load = useCallback(
    (url: string) => {
      const normalized = normalizeUrl(url);
      if (!normalized) return;
      updateActive({
        url: normalized,
        urlInput: normalized,
        title: titleFromUrl(normalized),
      });
    },
    [updateActive],
  );

  // The URL bar is the source of truth on Go — real-browser behaviour. If the
  // user edits the bar (even while a preset is selected), Enter/Go renders
  // exactly what they typed. Preset dropdown just seeds the bar and loads.
  const onGo = () => {
    if (!active_) return;
    load(active_.urlInput);
  };

  const onPresetChange = (id: string) => {
    if (!active_) return;
    updateActive({ presetId: id });
    const p = PRESETS.find((x) => x.id === id);
    if (!p || p.id === "custom") return;
    load(p.url);
  };

  const onNewTab = () => {
    const tab = makeTab("https://cyberspace.online", "cyberspace");
    setTabs((prev) => [...prev, tab]);
    setActiveId(tab.id);
  };

  const onCloseTab = (id: string) => {
    setTabs((prev) => {
      if (prev.length <= 1) return prev; // never close the last tab
      const filtered = prev.filter((tab) => tab.id !== id);
      if (id === activeId) {
        // pick the neighbor to the left, or the new first tab
        const idx = prev.findIndex((tab) => tab.id === id);
        const next = filtered[Math.max(0, idx - 1)] ?? filtered[0];
        if (next) setActiveId(next.id);
      }
      return filtered;
    });
  };

  // Pause the heavy <webview>/<iframe> when the panel is hidden so we're not
  // paying the decode/network cost in the background on a Pi 3B.
  useEffect(() => {
    if (!active) return;
  }, [active]);

  if (!active) return null;
  if (!active_) return null;

  return (
    <div className="web-panel">
      <div className="web-toolbar">
        <label className="web-label">
          <span className="dim">{t("web.tabsLabel", "tab")}</span>
          <select
            className="web-select"
            value={active_.id}
            onChange={(e) => setActiveId(e.target.value)}
            title={t("web.tabsHint", "switch open tabs")}
          >
            {tabs.map((tab, i) => (
              <option key={tab.id} value={tab.id}>
                {`${i + 1}. ${tab.title}`}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-ghost web-tab-new"
            onClick={onNewTab}
            title={t("web.newTab", "new tab")}
          >
            +
          </button>
          {tabs.length > 1 && (
            <button
              type="button"
              className="btn btn-ghost web-tab-close"
              onClick={() => onCloseTab(active_.id)}
              title={t("web.closeTab", "close tab")}
            >
              ×
            </button>
          )}
        </label>
        <label className="web-label">
          <span className="dim">{t("web.presetLabel", "app")}</span>
          <select
            className="web-select"
            value={active_.presetId}
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
            value={active_.urlInput}
            onChange={(e) => updateActive({ urlInput: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && onGo()}
          />
          <button type="button" className="btn btn-primary web-go" onClick={onGo}>
            {t("web.go", "go")}
          </button>
          {active_.url && !useWebview && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() =>
                window.open(active_.url, "_blank", "noopener,noreferrer")
              }
            >
              {t("web.openTab", "↗ tab")}
            </button>
          )}
        </div>
      </div>
      <p className="web-hint dim small">
        {useWebview
          ? t("web.hintWebview", "native webview — any site renders inline.")
          : t("web.hint", "sites that block embedding open in a new tab. custom URL loads here when possible.")}
      </p>
      <div className="web-frame-wrap">
        {active_.url ? (
          useWebview ? (
            // Electron <webview>. partition keeps cookies/storage for browsed
            // sites off the SPA's own origin. allowpopups is handled by
            // main.js's setWindowOpenHandler → shell.openExternal.
            // key={active_.id} forces remount per tab so the partition lines up.
            <webview
              key={active_.id}
              className="web-frame"
              src={active_.url}
              partition="persist:hosaka-browser"
              allowpopups={true}
            />
          ) : (
            <iframe
              key={active_.id}
              className="web-frame"
              title={t("web.frameTitle", "web")}
              src={active_.url}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
              referrerPolicy="no-referrer-when-downgrade"
            />
          )
        ) : (
          <div className="web-empty">
            {t("web.empty", "pick a preset or enter a URL and press go.")}
          </div>
        )}
      </div>
    </div>
  );
}
