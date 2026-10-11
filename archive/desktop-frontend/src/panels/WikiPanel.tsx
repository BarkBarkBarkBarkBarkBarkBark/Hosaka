/**
 * WikiPanel — random Wikipedia entry as a "what's out there?" tab.
 *
 * Hits the public REST summary endpoint (no API key required, CORS-enabled):
 *   https://<lang>.wikipedia.org/api/rest_v1/page/random/summary
 *
 * Keeps a small in-memory history so the operator can step backwards
 * through the last few rolls without re-fetching. The "another" button is
 * also wired to the spacebar / Enter when the panel is active.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import i18next from "../i18n";

type WikiSummary = {
  type: string;
  title: string;
  displaytitle?: string;
  extract: string;
  extract_html?: string;
  description?: string;
  thumbnail?: { source: string; width: number; height: number };
  content_urls?: { desktop?: { page?: string }; mobile?: { page?: string } };
  lang?: string;
};

type Props = { active: boolean };

const HISTORY_MAX = 25;

function endpoint(): string {
  // Use UI lang where Wikipedia has a sub-domain; fall back to en.
  const lang = (i18next.language || "en").split("-")[0];
  const known = ["en", "es", "fr", "it", "ja", "pt", "de"];
  const l = known.includes(lang) ? lang : "en";
  return `https://${l}.wikipedia.org/api/rest_v1/page/random/summary`;
}

export function WikiPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const [history, setHistory] = useState<WikiSummary[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inflight = useRef<AbortController | null>(null);

  const fetchOne = useCallback(async () => {
    inflight.current?.abort();
    const ac = new AbortController();
    inflight.current = ac;
    setLoading(true); setErr(null);
    try {
      const r = await fetch(endpoint(), {
        signal: ac.signal,
        headers: { accept: "application/json" },
      });
      if (!r.ok) throw new Error(`http ${r.status}`);
      const data: WikiSummary = await r.json();
      setHistory((prev) => {
        const next = [data, ...prev].slice(0, HISTORY_MAX);
        return next;
      });
      setIdx(0);
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setErr(t("wiki.errFetch", "could not reach wikipedia."));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // first load when the operator first taps the tab
  useEffect(() => {
    if (active && history.length === 0 && !loading) fetchOne();
  }, [active, history.length, loading, fetchOne]);

  // keyboard: space / enter = another, ←/→ = history navigate
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target && (e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); fetchOne(); }
      if (e.key === "ArrowLeft"  && idx < history.length - 1) setIdx(idx + 1);
      if (e.key === "ArrowRight" && idx > 0)                  setIdx(idx - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, fetchOne, idx, history.length]);

  const entry = history[idx] ?? null;
  const url = entry?.content_urls?.desktop?.page ?? entry?.content_urls?.mobile?.page;

  return (
    <div className="wiki-panel">
      <header className="panel-header">
        <h2>
          <span className="panel-glyph">W</span> {t("wiki.heading", "wikipedia roulette")}
        </h2>
        <p className="panel-sub">
          {t("wiki.sub", "a random article from the long quiet. press space for another.")}
        </p>
      </header>

      <div className="wiki-controls">
        <button className="btn btn-primary" onClick={fetchOne} disabled={loading}>
          {loading ? t("wiki.loading", "rolling…") : t("wiki.again", "↻ another")}
        </button>
        <div className="wiki-history">
          <button
            className="btn btn-ghost"
            onClick={() => setIdx(Math.min(history.length - 1, idx + 1))}
            disabled={idx >= history.length - 1}
            aria-label={t("wiki.prev", "previous")}
          >
            ◄
          </button>
          <span className="wiki-counter">
            {history.length === 0 ? "—" : `${idx + 1} / ${history.length}`}
          </span>
          <button
            className="btn btn-ghost"
            onClick={() => setIdx(Math.max(0, idx - 1))}
            disabled={idx <= 0}
            aria-label={t("wiki.next", "next")}
          >
            ►
          </button>
        </div>
        {url && (
          <a className="btn btn-ghost wiki-open" href={url} target="_blank" rel="noreferrer">
            {t("wiki.open", "open ↗")}
          </a>
        )}
      </div>

      <div className="wiki-stage">
        {err && <div className="wiki-err">{err}</div>}
        {!err && !entry && !loading && (
          <div className="wiki-empty">{t("wiki.empty", "press ↻ to roll an article")}</div>
        )}
        {entry && (
          <article className="wiki-article">
            {entry.thumbnail?.source && (
              <img
                className="wiki-thumb"
                src={entry.thumbnail.source}
                alt=""
                loading="lazy"
              />
            )}
            <div className="wiki-body">
              <h3
                className="wiki-title"
                dangerouslySetInnerHTML={{ __html: entry.displaytitle ?? entry.title }}
              />
              {entry.description && (
                <div className="wiki-desc">{entry.description}</div>
              )}
              <p className="wiki-extract">{entry.extract}</p>
            </div>
          </article>
        )}
      </div>
    </div>
  );
}
