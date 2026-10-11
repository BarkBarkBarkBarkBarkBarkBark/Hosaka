/**
 * AppStorePanel — Flathub catalog browser + staged-manifest installer.
 *
 * Search is served by the Electron host's `hosaka-apps:flathub-search` IPC
 * when present, and falls back to a direct Flathub JSON API call from the
 * browser. Installing actually means two things:
 *   1. Stage a YAML manifest under hosaka-apps/apps/ (audit trail).
 *   2. Trigger the existing `apps:install` path (mocked on macOS dev).
 */
import { useEffect, useState } from "react";
import { HOSAKA_APPS } from "../apps/hosakaApps";
import {
  getHosakaAppCapabilities,
  installHosakaApp,
  refreshHosakaAppsFromHost,
  searchFlathub,
  stageHosakaAppManifest,
  type FlathubHit,
  type HosakaAppCapabilities,
} from "../apps/flatpakBackend";

const SEED_QUERIES = ["spotify", "discord", "foliate", "vlc", "obs", "krita"];

type Status = { kind: "idle" | "info" | "ok" | "error"; text: string };

export function AppStorePanel() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<FlathubHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" });
  const [caps, setCaps] = useState<HosakaAppCapabilities | null>(null);
  const [stagedIds, setStagedIds] = useState<Set<string>>(
    () => new Set(HOSAKA_APPS.map((a) => a.flatpak_id).filter(Boolean)),
  );

  useEffect(() => {
    void getHosakaAppCapabilities().then(setCaps);
    void refreshHosakaAppsFromHost().then(() => {
      setStagedIds(new Set(HOSAKA_APPS.map((a) => a.flatpak_id).filter(Boolean)));
    });
    const onChange = () => setStagedIds(
      new Set(HOSAKA_APPS.map((a) => a.flatpak_id).filter(Boolean)),
    );
    window.addEventListener("hosaka:apps-changed", onChange);
    return () => window.removeEventListener("hosaka:apps-changed", onChange);
  }, []);

  async function runSearch(q: string) {
    setBusy(true);
    setStatus({ kind: "info", text: `searching flathub for "${q}"…` });
    const res = await searchFlathub(q);
    setBusy(false);
    if (!res.ok) {
      setStatus({ kind: "error", text: res.message ?? "flathub search failed." });
      setHits([]);
      return;
    }
    setHits(res.hits);
    setStatus({
      kind: res.hits.length ? "ok" : "info",
      text: res.hits.length ? `${res.hits.length} flathub hit(s).` : "no matches.",
    });
  }

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    void runSearch(q);
  }

  async function onInstall(hit: FlathubHit) {
    setBusy(true);
    setStatus({ kind: "info", text: `staging manifest for ${hit.name}…` });
    const staged = await stageHosakaAppManifest({
      flatpak_id: hit.id,
      name: hit.name || hit.id,
      description: hit.summary,
      category: hit.categories[0] ?? "other",
      provider: "Flathub",
    });
    if (!staged.ok) {
      // Already staged is not a hard error — proceed to install.
      if (!staged.message?.includes("already staged")) {
        setBusy(false);
        setStatus({ kind: "error", text: staged.message ?? "could not stage manifest." });
        return;
      }
    }
    setStatus({ kind: "info", text: `installing ${hit.name}…` });
    const id = staged.id ?? hit.id.split(".").pop() ?? hit.id;
    const installed = await installHosakaApp(id);
    setBusy(false);
    setStatus({
      kind: installed.ok ? "ok" : "error",
      text: installed.message,
    });
  }

  return (
    <div className="desktop-panel desktop-panel--directory">
      <div className="panel-header">
        <h2><span className="panel-glyph">⬚</span> app store</h2>
        <p className="panel-sub">
          flathub catalog · {caps
            ? caps.mocked
              ? "mock backend (dev — installs are simulated)"
              : caps.flatpakAvailable
                ? `${caps.host} · flatpak ready`
                : `${caps.host} · ${caps.note ?? "flatpak unavailable"}`
            : "checking host…"}
        </p>
      </div>

      <form className="app-store__search" onSubmit={onSubmit} style={{ padding: "0.5rem 1rem", display: "flex", gap: "0.5rem" }}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search flathub (e.g. spotify, discord, krita)…"
          aria-label="search flathub"
          style={{ flex: 1, padding: "0.4rem 0.6rem" }}
        />
        <button type="submit" className="btn" disabled={busy || !query.trim()}>
          search
        </button>
      </form>

      <div style={{ padding: "0 1rem 0.5rem", display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
        <span className="dim" style={{ fontSize: "0.85em" }}>try:</span>
        {SEED_QUERIES.map((q) => (
          <button
            key={q}
            type="button"
            className="btn"
            style={{ fontSize: "0.8em", padding: "0.2rem 0.5rem" }}
            onClick={() => { setQuery(q); void runSearch(q); }}
            disabled={busy}
          >
            {q}
          </button>
        ))}
      </div>

      {status.text && (
        <div
          style={{
            padding: "0.4rem 1rem",
            color: status.kind === "error" ? "#f88" : status.kind === "ok" ? "#9cf" : "#ccc",
            fontSize: "0.9em",
          }}
        >
          {status.text}
        </div>
      )}

      <ul className="app-store__hits" style={{ listStyle: "none", margin: 0, padding: "0 1rem 1rem" }}>
        {hits.map((hit) => {
          const already = stagedIds.has(hit.id);
          return (
            <li
              key={hit.id}
              style={{
                display: "flex",
                gap: "0.75rem",
                alignItems: "flex-start",
                padding: "0.6rem 0",
                borderBottom: "1px solid rgba(255,255,255,0.05)",
              }}
            >
              {hit.icon && (
                <img
                  src={hit.icon}
                  alt=""
                  width={48}
                  height={48}
                  style={{ borderRadius: 6, background: "rgba(255,255,255,0.04)" }}
                />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                  <strong>{hit.name || hit.id}</strong>
                  <code style={{ fontSize: "0.8em", opacity: 0.6 }}>{hit.id}</code>
                </div>
                <div className="dim" style={{ fontSize: "0.85em" }}>{hit.summary}</div>
              </div>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void onInstall(hit)}
                title={already ? "manifest already staged — re-install" : "stage manifest and install"}
              >
                {already ? "re-install" : "install"}
              </button>
            </li>
          );
        })}
      </ul>

      {HOSAKA_APPS.length > 0 && (
        <div style={{ padding: "0.5rem 1rem 1rem" }}>
          <h3 style={{ fontSize: "0.95em", marginBottom: "0.4rem" }}>staged manifests</h3>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, fontSize: "0.85em" }}>
            {HOSAKA_APPS.map((app) => (
              <li key={app.id} style={{ padding: "0.2rem 0" }}>
                <strong>{app.name}</strong>{" "}
                <code style={{ opacity: 0.6 }}>{app.flatpak_id}</code>{" "}
                <span className="dim">· {app.category}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
