/**
 * ReadingPanel — volume reader.
 *
 * Each "volume" is a GitHub Pages repo. We fetch raw markdown from
 * raw.githubusercontent.com (CORS-friendly) and render it natively with
 * `marked` — no iframes, nothing to be blocked by X-Frame-Options.
 *
 * Volume schema (public/reading/collections.json):
 *   {
 *     id, title, summary?, description?, homepage,
 *     source: { type: "github-raw", repo, branch, basePath },
 *     toc:    [ { section } | { slug, title, path, summary? } ],
 *     aliases?: string[]
 *   }
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";
import { useTranslation } from "../i18n";

type GithubRawSource = {
  type: "github-raw";
  repo: string;
  branch: string;
  basePath: string;
};

type TocSection = { section: string };
type TocDoc = {
  slug: string;
  title: string;
  path: string;
  summary?: string;
};
type TocEntry = TocSection | TocDoc;

type Volume = {
  id: string;
  title: string;
  summary?: string;
  description?: string;
  homepage?: string;
  source: GithubRawSource;
  toc: TocEntry[];
  aliases?: string[];
};

type Props = { active: boolean };

function isDoc(entry: TocEntry): entry is TocDoc {
  return (entry as TocDoc).path !== undefined;
}

function isValidVolume(item: unknown): item is Volume {
  if (!item || typeof item !== "object") return false;
  const v = item as Partial<Volume>;
  if (!v.id || !v.title || !v.source || !Array.isArray(v.toc)) return false;
  if (v.source.type !== "github-raw") return false;
  if (!v.source.repo || !v.source.branch || typeof v.source.basePath !== "string") return false;
  return true;
}

function rawUrl(volume: Volume, path: string): string {
  const { repo, branch, basePath } = volume.source;
  const base = basePath ? `${basePath.replace(/\/$/, "")}/` : "";
  const clean = path.replace(/^\//, "");
  return `https://raw.githubusercontent.com/${repo}/${encodeURIComponent(branch)}/${base}${clean}`;
}

/** Resolve a free-form token into a (volume, doc?) pair. */
function resolveTarget(
  value: string,
  volumes: Volume[],
): { volumeId: string; docSlug: string | null } | null {
  const q = value.trim().toLowerCase();
  if (!q) return null;

  for (const v of volumes) {
    for (const entry of v.toc) {
      if (isDoc(entry) && entry.slug.toLowerCase() === q) {
        return { volumeId: v.id, docSlug: entry.slug };
      }
    }
  }

  for (const v of volumes) {
    if (v.id.toLowerCase() === q) return { volumeId: v.id, docSlug: null };
    if (v.aliases?.some((a) => a.toLowerCase() === q)) {
      return { volumeId: v.id, docSlug: null };
    }
  }

  return null;
}

marked.setOptions({ gfm: true, breaks: false });

const docCache = new Map<string, string>();

async function fetchMarkdown(url: string): Promise<string> {
  const cached = docCache.get(url);
  if (cached !== undefined) return cached;
  const res = await fetch(url, { headers: { accept: "text/plain" } });
  if (!res.ok) throw new Error(`http ${res.status}`);
  const text = await res.text();
  docCache.set(url, text);
  return text;
}

export function ReadingPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const [volumes, setVolumes] = useState<Volume[]>([]);
  const [volumeId, setVolumeId] = useState<string | null>(null);
  const [docSlug, setDocSlug] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [loadingIndex, setLoadingIndex] = useState(false);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [html, setHtml] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setLoadingIndex(true);
    fetch("/reading/collections.json")
      .then((r) => r.json())
      .then((d: unknown) => {
        if (!Array.isArray(d)) {
          setVolumes([]);
          return;
        }
        setVolumes(d.filter(isValidVolume));
      })
      .catch(() => setVolumes([]))
      .finally(() => setLoadingIndex(false));
  }, []);

  useEffect(() => {
    if (active && !volumeId && volumes.length > 0) {
      setVolumeId(volumes[0].id);
      setExpanded((s) => {
        if (s.has(volumes[0].id)) return s;
        const next = new Set(s);
        next.add(volumes[0].id);
        return next;
      });
    }
  }, [active, volumes, volumeId]);

  useEffect(() => {
    if (!volumeId || volumes.length === 0) return;
    if (!volumes.some((v) => v.id === volumeId)) {
      setVolumeId(volumes[0]?.id ?? null);
      setDocSlug(null);
    }
  }, [volumes, volumeId]);

  const selectedVolume = useMemo(
    () => volumes.find((v) => v.id === volumeId) ?? null,
    [volumes, volumeId],
  );

  const selectedDoc = useMemo(() => {
    if (!selectedVolume || !docSlug) return null;
    const hit = selectedVolume.toc.find((e) => isDoc(e) && e.slug === docSlug);
    return hit && isDoc(hit) ? hit : null;
  }, [selectedVolume, docSlug]);

  useEffect(() => {
    if (!selectedVolume) return;
    if (docSlug && selectedVolume.toc.some((e) => isDoc(e) && e.slug === docSlug)) {
      return;
    }
    const firstDoc = selectedVolume.toc.find(isDoc);
    setDocSlug(firstDoc ? firstDoc.slug : null);
  }, [selectedVolume, docSlug]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedVolume || !selectedDoc) {
      setHtml("");
      setError(null);
      return;
    }
    const url = rawUrl(selectedVolume, selectedDoc.path);
    setLoadingDoc(true);
    setError(null);
    fetchMarkdown(url)
      .then(async (md) => {
        if (cancelled) return;
        const rendered = await marked.parse(md);
        if (cancelled) return;
        setHtml(rendered);
      })
      .catch(() => {
        if (cancelled) return;
        setError(t("reading.errorFetch", "could not reach the volume. signal was quiet."));
        setHtml("");
      })
      .finally(() => {
        if (!cancelled) setLoadingDoc(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedVolume, selectedDoc, t]);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [html, docSlug, volumeId]);

  const onReadEvent = useCallback(
    (value: string) => {
      const hit = resolveTarget(value, volumes);
      if (!hit) return;
      setVolumeId(hit.volumeId);
      setExpanded((s) => {
        if (s.has(hit.volumeId)) return s;
        const next = new Set(s);
        next.add(hit.volumeId);
        return next;
      });
      if (hit.docSlug) setDocSlug(hit.docSlug);
    },
    [volumes],
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const value = (e as CustomEvent<string>).detail;
      if (value) onReadEvent(value);
    };
    window.addEventListener("hosaka:read", handler as EventListener);
    return () => window.removeEventListener("hosaka:read", handler as EventListener);
  }, [onReadEvent]);

  const toggleVolume = (id: string) => {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setVolumeId(id);
  };

  const pickDoc = (volId: string, slug: string) => {
    setVolumeId(volId);
    setDocSlug(slug);
    setError(null);
    setExpanded((s) => {
      if (s.has(volId)) return s;
      const next = new Set(s);
      next.add(volId);
      return next;
    });
  };

  return (
    <div className="reading-wrap">
      <div className="reading-sidebar">
        <div className="reading-sidebar-head">
          <span className="panel-glyph">❑</span> {t("reading.sidebarHead", "volumes")}
        </div>

        {loadingIndex && <p className="reading-loading">{t("reading.loading")}</p>}

        <div className="reading-volume-list">
          {volumes.map((v) => {
            const isExpanded = expanded.has(v.id);
            const isSelected = v.id === volumeId;
            return (
              <div
                key={v.id}
                className={`reading-volume ${isExpanded ? "is-open" : ""} ${
                  isSelected ? "is-selected" : ""
                }`}
              >
                <button
                  type="button"
                  className={`reading-volume-btn ${isSelected ? "is-active" : ""}`}
                  onClick={() => toggleVolume(v.id)}
                  aria-expanded={isExpanded}
                >
                  <span className={`reading-volume-chevron ${isExpanded ? "is-open" : ""}`} aria-hidden="true">
                    ▸
                  </span>
                  <span className="reading-volume-label">
                    <span className="reading-volume-title">{v.title}</span>
                    <span className="reading-volume-meta">
                      {v.summary ?? v.source.repo}
                    </span>
                  </span>
                </button>
                {isExpanded && (
                  <ul className="reading-toc">
                    {v.toc.map((entry, i) =>
                      isDoc(entry) ? (
                        <li key={entry.slug}>
                          <button
                            type="button"
                            className={`reading-toc-entry ${
                              isSelected && entry.slug === docSlug ? "is-active" : ""
                            }`}
                            onClick={() => pickDoc(v.id, entry.slug)}
                            title={entry.summary ?? entry.title}
                          >
                            <span className="reading-toc-title">{entry.title}</span>
                            {entry.summary && (
                              <span className="reading-toc-summary dim small">
                                {entry.summary}
                              </span>
                            )}
                          </button>
                        </li>
                      ) : (
                        <li key={`sec-${i}`} className="reading-toc-section">
                          {entry.section}
                        </li>
                      ),
                    )}
                  </ul>
                )}
              </div>
            );
          })}
        </div>

        <div className="reading-sidebar-foot">
          <button
            className="btn btn-ghost reading-order-btn"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("hosaka:open-tab", { detail: "terminal" }),
              )
            }
          >
            {t("reading.orderBtn")}
          </button>
        </div>
      </div>

      <div className="reading-content" ref={contentRef}>
        {loadingIndex && !selectedVolume && (
          <p className="reading-loading">{t("reading.loading")}</p>
        )}

        {selectedVolume && (
          <div className="reading-volume-view">
            <header className="reading-volume-head">
              <div className="reading-volume-copy">
                <h2 className="reading-volume-heading">{selectedVolume.title}</h2>
                {(selectedVolume.description || selectedVolume.summary) && (
                  <p className="reading-volume-desc">
                    {selectedVolume.description ?? selectedVolume.summary}
                  </p>
                )}
                <p className="reading-volume-source dim small">
                  <code>
                    {selectedVolume.source.repo}@{selectedVolume.source.branch}:{selectedVolume.source.basePath}
                  </code>
                </p>
              </div>
              {selectedVolume.homepage && (
                <button
                  type="button"
                  className="btn btn-ghost reading-collection-link"
                  onClick={() =>
                    window.open(selectedVolume.homepage, "_blank", "noopener,noreferrer")
                  }
                  title={selectedVolume.homepage}
                >
                  {selectedVolume.homepage.includes("github.io")
                    ? t("reading.openPages", "gh-pages ↗")
                    : t("reading.openRepo", "source ↗")}
                </button>
              )}
            </header>

            {!selectedDoc && (
              <p className="reading-empty">
                {t("reading.pickDoc", "select a chapter from the sidebar.")}
              </p>
            )}

            {selectedDoc && (
              <article className="reading-article">
                {loadingDoc && (
                  <p className="reading-loading">{t("reading.loadingDoc", "tuning…")}</p>
                )}
                {error && !loadingDoc && (
                  <div className="reading-error err">
                    <p>{error}</p>
                    <p className="dim small">
                      <code>{rawUrl(selectedVolume, selectedDoc.path)}</code>
                    </p>
                  </div>
                )}
                {!loadingDoc && !error && (
                  <div
                    className="reading-markdown"
                    dangerouslySetInnerHTML={{ __html: html }}
                  />
                )}
              </article>
            )}
          </div>
        )}

        {!loadingIndex && !selectedVolume && (
          <div className="reading-empty">
            <p>{t("reading.emptySelect", "select a volume from the sidebar.")}</p>
            <p
              className="dim"
              dangerouslySetInnerHTML={{ __html: t("reading.emptyHint") }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
