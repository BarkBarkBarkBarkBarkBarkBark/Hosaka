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

type Props = { active: boolean };

export function WebPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  // cyberspace.online is the canonical "front door" for Hosaka — opening the
  // web panel should funnel users into the community, not a random encyclopedia
  // article. Operators can always pick a preset or type a URL.
  const [presetId, setPresetId] = useState("cyberspace");
  const [urlInput, setUrlInput] = useState("https://cyberspace.online");
  const [src, setSrc] = useState<string | null>("https://cyberspace.online");

  // We only evaluate once per mount — the kiosk host can't hot-swap the
  // preload bridge in. Plain browsers never get it. Either way the value
  // is stable for the life of the session.
  const [mode] = useState(() => getBrowserMode());
  const useWebview = mode === "native-webview";

  const preset = useMemo(
    () => PRESETS.find((p) => p.id === presetId) ?? PRESETS[1],
    [presetId],
  );

  const load = useCallback(
    (url: string) => {
      const normalized = normalizeUrl(url);
      if (!normalized) return;
      setSrc(normalized);
      setUrlInput(normalized);
    },
    [],
  );

  const applyPreset = useCallback(
    (p: Preset, customUrl?: string) => {
      if (p.id === "custom") {
        load(customUrl ?? urlInput);
        return;
      }
      load(p.url);
    },
    [urlInput, load],
  );

  // The URL bar is the source of truth on Go — real-browser behaviour. If the
  // user edits the bar (even while a preset is selected), Enter/Go renders
  // exactly what they typed. Preset dropdown just seeds the bar and loads.
  const onGo = () => load(urlInput);

  const onPresetChange = (id: string) => {
    setPresetId(id);
    const p = PRESETS.find((x) => x.id === id);
    if (!p) return;
    if (p.id === "custom") {
      setSrc(null);
      return;
    }
    load(p.url);
  };

  // Pause the heavy <webview>/<iframe> when the panel is hidden so we're not
  // paying the decode/network cost in the background on a Pi 3B.
  useEffect(() => {
    if (!active) return;
  }, [active]);

  if (!active) return null;

  return (
    <div className="web-panel">
      <div className="web-toolbar">
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
          {src && !useWebview && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => window.open(src, "_blank", "noopener,noreferrer")}
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
        {src ? (
          useWebview ? (
            // Electron <webview>. partition keeps cookies/storage for browsed
            // sites off the SPA's own origin. allowpopups is handled by
            // main.js's setWindowOpenHandler → shell.openExternal.
            <webview
              className="web-frame"
              src={src}
              partition="persist:hosaka-browser"
              allowpopups={true}
            />
          ) : (
            <iframe
              className="web-frame"
              title={t("web.frameTitle", "web")}
              src={src}
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
