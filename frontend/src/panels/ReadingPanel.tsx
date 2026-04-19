import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "../i18n";
import { marked } from "marked";
import i18next from "../i18n";

// Marked is configured once at module load. GFM is on (tables, strikethrough,
// task-list checkboxes, autolinks); breaks: false to match commonmark prose.
// We intentionally do NOT install a sanitizer — library content is authored
// in this repo, not user-supplied, so there's nothing to sanitize against.
marked.setOptions({ gfm: true, breaks: false });

type LibraryEntry = {
  slug: string;
  title: string;
  author: string;
  date: string;
  tags: string[];
  summary: string;
};

type Props = { active: boolean };

function libraryPath(slug: string): string {
  const lang = i18next.language?.split("-")[0] ?? "en";
  return `/library/${lang}/${slug}.md`;
}

function libraryFallback(slug: string): string {
  return `/library/en/${slug}.md`;
}

export function ReadingPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/library/index.json")
      .then((r) => r.json())
      .then((d: LibraryEntry[]) => setEntries(d))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const onSelect = (e: Event) => {
      const slug = (e as CustomEvent<string>).detail;
      if (slug) setSelected(slug);
    };
    window.addEventListener("hosaka:read", onSelect as EventListener);
    return () =>
      window.removeEventListener("hosaka:read", onSelect as EventListener);
  }, []);

  useEffect(() => {
    if (!selected) {
      setContent("");
      return;
    }
    setLoading(true);
    const errMsg = t("reading.errorNotFound");
    fetch(libraryPath(selected))
      .then((r) => {
        if (r.ok) return r.text();
        return fetch(libraryFallback(selected)).then((fb) =>
          fb.ok ? fb.text() : errMsg,
        );
      })
      .then((txt) => setContent(txt))
      .catch(() => setContent(errMsg))
      .finally(() => setLoading(false));
  }, [selected, t]);

  useEffect(() => {
    if (active && !selected && entries.length > 0) {
      setSelected(entries[0].slug);
    }
  }, [active, entries, selected]);

  const entry = entries.find((e) => e.slug === selected);

  // marked is sync in our config (no async extensions); the cast is safe.
  const html = useMemo(() => (content ? (marked.parse(content) as string) : ""), [content]);

  return (
    <div className="reading-wrap">
      <div className="reading-sidebar">
        <div className="reading-sidebar-head">
          <span className="panel-glyph">❑</span> {t("reading.sidebarHead")}
        </div>
        {entries.map((e) => (
          <button
            key={e.slug}
            className={`reading-entry ${selected === e.slug ? "is-active" : ""}`}
            onClick={() => setSelected(e.slug)}
          >
            <span className="reading-entry-title">{e.title}</span>
            <span className="reading-entry-meta">
              {e.author} · {e.date}
            </span>
          </button>
        ))}
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

      <div className="reading-content">
        {loading && (
          <p className="reading-loading">{t("reading.loading")}</p>
        )}
        {!loading && content && (
          <>
            {entry && (
              <div className="reading-entry-tags">
                {entry.tags.map((tag) => (
                  <span key={tag} className="reading-tag">
                    {tag}
                  </span>
                ))}
              </div>
            )}
            <div className="reading-md" dangerouslySetInnerHTML={{ __html: html }} />
          </>
        )}
        {!loading && !content && (
          <div className="reading-empty">
            <p>{t("reading.emptySelect")}</p>
            <p className="dim" dangerouslySetInnerHTML={{ __html: t("reading.emptyHint") }} />
          </div>
        )}
      </div>
    </div>
  );
}
