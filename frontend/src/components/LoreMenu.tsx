import { useEffect, useState } from "react";
import library from "../../public/library/index.json";
import { useTranslation } from "../i18n";

export function LoreMenu({ initialSlug }: { initialSlug: string | null }) {
  const { t } = useTranslation("gui");
  const [slug, setSlug] = useState(initialSlug);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const entry = library.find((item) => item.slug === slug);

  useEffect(() => {
    if (!entry) return;
    const controller = new AbortController();
    setText("");
    setError("");
    setLoading(true);
    void fetch(`${import.meta.env.BASE_URL}library/en/${entry.slug}.md`, {
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setText(await response.text());
    }).catch((err: unknown) => {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [entry]);

  return (
    <section className="deck-lore">
      {entry ? (
        <>
          <button onClick={() => setSlug(null)}>{t("loreArchive")}</button>
          <h2>{entry.title}</h2>
          {loading && <p role="status">{t("working")}</p>}
          {error && <p role="alert" className="deck-error">{t("loreFailed")} {error}</p>}
          {text && <pre className="deck-lore-record">{text}</pre>}
        </>
      ) : (
        <>
          <h2>{t("loreArchive")}</h2>
          <ul className="deck-device-list">
            {library.map((record) => (
              <li key={record.slug}>
                <button onClick={() => setSlug(record.slug)}>
                  {record.title}<small>{record.summary}</small>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
