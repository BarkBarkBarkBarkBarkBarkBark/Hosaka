import { useEffect, useState } from "react";
import help from "../../../docs/api.md?raw";
import { useTranslation } from "../i18n";

type Operation = { method: string; path: string; summary: string; details: string };

function operationsFromSchema(value: unknown): Operation[] {
  if (!value || typeof value !== "object" || !("paths" in value)
    || !value.paths || typeof value.paths !== "object") {
    throw new Error("Invalid OpenAPI schema: missing paths.");
  }
  const operations: Operation[] = [];
  for (const [path, item] of Object.entries(value.paths)) {
    if (!item || typeof item !== "object") continue;
    for (const [method, operation] of Object.entries(item)) {
      if (!["get", "post", "put", "patch", "delete", "head", "options"].includes(method)
        || !operation || typeof operation !== "object") continue;
      operations.push({
        method: method.toUpperCase(),
        path,
        summary: "summary" in operation && typeof operation.summary === "string" ? operation.summary : "",
        details: JSON.stringify(operation, null, 2),
      });
    }
  }
  return operations;
}

export function ApiHelp() {
  const { t } = useTranslation("gui");
  const [operations, setOperations] = useState<Operation[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/openapi.json", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const schema: unknown = await response.json();
        setOperations(operationsFromSchema(schema));
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const search = query.trim().toLowerCase();
  const matching = operations.filter((operation) =>
    `${operation.method} ${operation.path} ${operation.summary}`.toLowerCase().includes(search));

  return (
    <section className="deck-settings deck-api-help">
      <h2>{t("apiHelp")}</h2>
      <p className="deck-hint">{t("apiReadOnly")}</p>
      <details><summary>{t("apiGuide")}</summary><pre className="deck-lore-record">{help}</pre></details>
      <p><a href="/openapi.json" target="_blank" rel="noreferrer">{t("openApiSchema")}</a></p>
      <label>{t("apiSearch")}<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      {loading && <p role="status">{t("working")}</p>}
      {error && <p role="alert" className="deck-error">{t("apiFailed")} {error}</p>}
      {!loading && !error && matching.length === 0 && <p>{t("apiNoMatches")}</p>}
      {matching.map((operation) => (
        <details key={`${operation.method} ${operation.path}`} className="deck-api-operation">
          <summary>{operation.method} {operation.path}<small>{operation.summary}</small></summary>
          <pre className="deck-lore-record">{operation.details}</pre>
        </details>
      ))}
    </section>
  );
}
