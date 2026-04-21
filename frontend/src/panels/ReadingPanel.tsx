import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "../i18n";

type ReadingCollection = {
  id: string;
  title: string;
  summary?: string;
  description?: string;
  url: string;
  aliases?: string[];
};

type Props = { active: boolean };

function isValidCollection(item: unknown): item is ReadingCollection {
  if (!item || typeof item !== "object") return false;
  const c = item as Partial<ReadingCollection>;
  if (!c.id || !c.title || !c.url) return false;
  try {
    const u = new URL(c.url);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function resolveCollectionId(value: string, collections: ReadingCollection[]): string | null {
  const q = value.trim().toLowerCase();
  if (!q) return null;
  const hit = collections.find(
    (c) =>
      c.id.toLowerCase() === q ||
      (Array.isArray(c.aliases) && c.aliases.some((a) => a.toLowerCase() === q)),
  );
  return hit?.id ?? null;
}

export function ReadingPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const [collections, setCollections] = useState<ReadingCollection[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch("/reading/collections.json")
      .then((r) => r.json())
      .then((d: unknown) => {
        if (!Array.isArray(d)) {
          setCollections([]);
          return;
        }
        setCollections(d.filter(isValidCollection));
      })
      .catch(() => setCollections([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const onSelect = (e: Event) => {
      const value = (e as CustomEvent<string>).detail;
      if (!value) return;
      const nextId = resolveCollectionId(value, collections);
      if (nextId) setSelectedId(nextId);
    };
    window.addEventListener("hosaka:read", onSelect as EventListener);
    return () =>
      window.removeEventListener("hosaka:read", onSelect as EventListener);
  }, [collections]);

  useEffect(() => {
    if (active && !selectedId && collections.length > 0) {
      setSelectedId(collections[0].id);
    }
  }, [active, collections, selectedId]);

  useEffect(() => {
    if (!selectedId || collections.length === 0) return;
    if (!collections.some((c) => c.id === selectedId)) {
      setSelectedId(collections[0]?.id ?? null);
    }
  }, [collections, selectedId]);

  const selected = useMemo(
    () => collections.find((c) => c.id === selectedId) ?? null,
    [collections, selectedId],
  );

  return (
    <div className="reading-wrap">
      <div className="reading-sidebar">
        <div className="reading-sidebar-head">
          <span className="panel-glyph">❑</span> {t("reading.sidebarHead", "collections")}
        </div>
        {collections.map((c) => (
          <button
            key={c.id}
            className={`reading-entry ${selectedId === c.id ? "is-active" : ""}`}
            onClick={() => setSelectedId(c.id)}
          >
            <span className="reading-entry-title">{c.title}</span>
            <span className="reading-entry-meta">{c.summary ?? c.id}</span>
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
        {loading && <p className="reading-loading">{t("reading.loading")}</p>}
        {!loading && selected && (
          <div className="reading-collection">
            <div className="reading-collection-head">
              <div className="reading-collection-copy">
                <h2 className="reading-collection-title">{selected.title}</h2>
                {(selected.description || selected.summary) && (
                  <p className="reading-collection-desc">
                    {selected.description ?? selected.summary}
                  </p>
                )}
              </div>
              <button
                type="button"
                className="btn btn-ghost reading-collection-link"
                onClick={() =>
                  window.open(selected.url, "_blank", "noopener,noreferrer")
                }
              >
                {t("reading.openCollection", "open collection ↗")}
              </button>
            </div>
            <div className="reading-frame-wrap">
              <iframe
                className="reading-frame"
                title={selected.title}
                src={selected.url}
                sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
          </div>
        )}
        {!loading && !selected && (
          <div className="reading-empty">
            <p>{t("reading.emptySelect", "select a collection from the sidebar.")}</p>
            <p className="dim" dangerouslySetInnerHTML={{ __html: t("reading.emptyHint") }} />
          </div>
        )}
      </div>
    </div>
  );
}
