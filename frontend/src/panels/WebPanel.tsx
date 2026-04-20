/**
 * WebPanel — minimal browser + preset “apps”.
 *
 * Many big sites (YouTube, Instagram, Discord, …) send X-Frame-Options and
 * refuse to render inside an iframe. For those we open a new browser tab /
 * window (`mode: "window"`). Embed-friendly pages use `mode: "iframe"`.
 *
 * All heavy UI is this one lazy chunk; iframe `src` only loads after you pick
 * a preset or press Go.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "../i18n";

type LoadMode = "iframe" | "window";

type Preset = {
  id: string;
  labelKey: string;
  url: string;
  mode: LoadMode;
};

const PRESETS: Preset[] = [
  { id: "custom", labelKey: "web.presetCustom", url: "", mode: "iframe" },
  { id: "wiki", labelKey: "web.presetWiki", url: "https://en.wikipedia.org/wiki/Special:Random", mode: "iframe" },
  { id: "hn", labelKey: "web.presetHn", url: "https://news.ycombinator.com", mode: "iframe" },
  { id: "gh", labelKey: "web.presetGh", url: "https://github.com", mode: "iframe" },
  { id: "archive", labelKey: "web.presetArchive", url: "https://archive.org", mode: "iframe" },
  { id: "reddit", labelKey: "web.presetReddit", url: "https://old.reddit.com", mode: "iframe" },
  { id: "yt", labelKey: "web.presetYt", url: "https://m.youtube.com", mode: "window" },
  { id: "tiktok", labelKey: "web.presetTiktok", url: "https://www.tiktok.com", mode: "window" },
  { id: "ig", labelKey: "web.presetIg", url: "https://www.instagram.com", mode: "window" },
  { id: "discord", labelKey: "web.presetDiscord", url: "https://discord.com/app", mode: "window" },
  { id: "twitch", labelKey: "web.presetTwitch", url: "https://www.twitch.tv", mode: "window" },
  { id: "reddit_new", labelKey: "web.presetRedditNew", url: "https://www.reddit.com", mode: "window" },
  { id: "mastodon", labelKey: "web.presetMastodon", url: "https://mastodon.social/explore", mode: "iframe" },
  { id: "lobsters", labelKey: "web.presetLobsters", url: "https://lobste.rs", mode: "iframe" },
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
  const [presetId, setPresetId] = useState("wiki");
  const [urlInput, setUrlInput] = useState("https://en.wikipedia.org");
  const [iframeSrc, setIframeSrc] = useState<string | null>(
    "https://en.wikipedia.org/wiki/Special:Random",
  );
  const [lastExternal, setLastExternal] = useState<string | null>(null);

  const preset = useMemo(
    () => PRESETS.find((p) => p.id === presetId) ?? PRESETS[1],
    [presetId],
  );

  const applyPreset = useCallback(
    (p: Preset, customUrl?: string) => {
      if (p.id === "custom") {
        const u = normalizeUrl(customUrl ?? urlInput);
        if (!u) return;
        setIframeSrc(u);
        setUrlInput(u);
        return;
      }
      if (p.mode === "window") {
        window.open(p.url, "_blank", "noopener,noreferrer");
        setLastExternal(p.url);
        setIframeSrc(null);
        return;
      }
      setIframeSrc(p.url);
      setLastExternal(null);
    },
    [urlInput],
  );

  const onGo = () => applyPreset(preset);

  const onPresetChange = (id: string) => {
    setPresetId(id);
    const p = PRESETS.find((x) => x.id === id);
    if (!p) return;
    if (p.id === "custom") {
      setIframeSrc(null);
      return;
    }
    if (p.mode === "window") {
      window.open(p.url, "_blank", "noopener,noreferrer");
      setLastExternal(p.url);
      setIframeSrc(null);
      return;
    }
    setIframeSrc(p.url);
    setLastExternal(null);
  };

  // Listen for shell shortcuts like /reddit, /tiktok, /discord.
  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      if (id) onPresetChange(id);
    };
    window.addEventListener("hosaka:web-preset", handler as EventListener);
    return () => window.removeEventListener("hosaka:web-preset", handler as EventListener);
    // onPresetChange is stable (only depends on state setters + PRESETS const)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!active) return null;

  return (
    <div className="web-panel">
      {/* ── social quick-launch bar ─── */}
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
          {iframeSrc && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => window.open(iframeSrc, "_blank", "noopener,noreferrer")}
            >
              {t("web.openTab", "↗ tab")}
            </button>
          )}
        </div>
      </div>
      <p className="web-hint dim small">{t("web.hint", "sites that block embedding open in a new tab. custom URL loads here when possible.")}</p>
      {lastExternal && (
        <p className="web-external-note">
          {t("web.openedExternal", "opened:")} <code>{lastExternal}</code>
        </p>
      )}
      <div className="web-frame-wrap">
        {iframeSrc ? (
          <iframe
            className="web-frame"
            title={t("web.frameTitle", "web")}
            src={iframeSrc}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
            referrerPolicy="no-referrer-when-downgrade"
          />
        ) : (
          <div className="web-empty">
            {t("web.empty", "pick a preset or enter a URL and press go.")}
          </div>
        )}
      </div>
    </div>
  );
}
