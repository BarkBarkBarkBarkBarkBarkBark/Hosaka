/**
 * BooksPanel — Amazon books search + discovery.
 *
 * Calls the operator-hosted /api/books proxy (which wraps the Amazon Product
 * Advertising API v5 with server-side signing). If the proxy is not
 * configured, the panel shows a friendly "not wired up yet" message so it
 * degrades gracefully on static deployments with no API key.
 *
 * Purchase / reading flows open in a new tab (Amazon's checkout and Kindle
 * Cloud Reader do not permit iframe embedding). We only display metadata here.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";

type BookResult = {
  asin: string;
  title: string;
  authors: string[];
  imageUrl?: string;
  price?: string;
  url: string;
  kindleUrl?: string;
  binding?: string;
};

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; results: BookResult[] }
  | { status: "unconfigured" };

const API_BASE: string =
  (import.meta.env.VITE_HOSAKA_API_BASE as string | undefined) ?? "";

async function searchBooks(query: string): Promise<SearchState> {
  try {
    const res = await fetch(
      `${API_BASE}/api/books?q=${encodeURIComponent(query)}`,
    );
    if (res.status === 501 || res.status === 404) {
      return { status: "unconfigured" };
    }
    if (res.status === 503) {
      return { status: "unconfigured" };
    }
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      return { status: "error", message: body.error ?? `http ${res.status}` };
    }
    const data = (await res.json()) as { results?: BookResult[] };
    return { status: "ok", results: data.results ?? [] };
  } catch {
    return { status: "unconfigured" };
  }
}

type Props = { active: boolean };

export function BooksPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Focus the search box when the panel becomes active.
  useEffect(() => {
    if (active) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [active]);

  const doSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setState({ status: "loading" });
    const result = await searchBooks(trimmed);
    setState(result);
  }, []);

  // Listen for shell /books <query> command.
  useEffect(() => {
    const handler = (e: Event) => {
      const q = (e as CustomEvent<string>).detail;
      if (q) {
        setQuery(q);
        void doSearch(q);
      }
    };
    window.addEventListener("hosaka:books-search", handler as EventListener);
    return () =>
      window.removeEventListener("hosaka:books-search", handler as EventListener);
  }, [doSearch]);

  if (!active) return null;

  return (
    <div className="books-panel">
      <header className="panel-header">
        <h2>
          <span className="panel-glyph">📖</span>{" "}
          {t("books.heading", "books")}
        </h2>
        <p className="panel-sub">{t("books.sub", "search amazon books. browse here, buy there.")}</p>
      </header>

      <div className="books-search-row">
        <input
          ref={inputRef}
          type="text"
          className="books-input"
          placeholder={t("books.placeholder", "search for a title, author, or ISBN…")}
          value={query}
          spellCheck={false}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doSearch(query)}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={state.status === "loading" || !query.trim()}
          onClick={() => doSearch(query)}
        >
          {state.status === "loading"
            ? t("books.searching", "searching…")
            : t("books.search", "search")}
        </button>
      </div>

      <div className="books-stage">
        {state.status === "idle" && (
          <div className="books-empty">
            {t("books.idle", "search for a book to begin.")}
          </div>
        )}

        {state.status === "unconfigured" && (
          <div className="books-unconfigured">
            <p>{t("books.unconfigured", "the book relay isn't wired up yet.")}</p>
            <p className="dim small">
              {t(
                "books.unconfiguredHint",
                "to enable: add AMAZON_PA_ACCESS_KEY, AMAZON_PA_SECRET_KEY, AMAZON_PA_PARTNER_TAG, and AMAZON_PA_REGION to your deployment environment, then redeploy.",
              )}
            </p>
            <p className="dim small">
              {t(
                "books.unconfiguredFallback",
                "in the meantime, try the web panel → amazon, or ask the orb for a recommendation.",
              )}
            </p>
          </div>
        )}

        {state.status === "error" && (
          <div className="books-error err">{state.message}</div>
        )}

        {state.status === "ok" && state.results.length === 0 && (
          <div className="books-empty">
            {t("books.noResults", "no results. the signal was quiet.")}
          </div>
        )}

        {state.status === "ok" && state.results.length > 0 && (
          <ul className="books-list">
            {state.results.map((book) => (
              <li key={book.asin} className="books-item">
                {book.imageUrl && (
                  <img
                    className="books-cover"
                    src={book.imageUrl}
                    alt=""
                    loading="lazy"
                  />
                )}
                <div className="books-meta">
                  <div className="books-title">{book.title}</div>
                  {book.authors.length > 0 && (
                    <div className="books-authors dim small">
                      {book.authors.join(", ")}
                    </div>
                  )}
                  {book.binding && (
                    <div className="books-binding dim small">{book.binding}</div>
                  )}
                  {book.price && (
                    <div className="books-price">{book.price}</div>
                  )}
                  <div className="books-actions">
                    <a
                      href={book.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="btn btn-primary books-buy-btn"
                    >
                      {t("books.buyOnAmazon", "buy on amazon ↗")}
                    </a>
                    {book.kindleUrl && (
                      <a
                        href={book.kindleUrl}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="btn books-kindle-btn"
                      >
                        {t("books.kindle", "kindle ↗")}
                      </a>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
