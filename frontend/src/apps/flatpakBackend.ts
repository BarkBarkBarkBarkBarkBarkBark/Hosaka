import {
  getHosakaAppById,
  refreshHosakaApps,
  resolveHosakaAppId,
} from "./hosakaApps";

export type HosakaAppHostResponse = {
  ok: boolean;
  appId?: string;
  manifestFound?: boolean;
  installed?: boolean;
  flatpakAvailable?: boolean;
  flathubConfigured?: boolean;
  launched?: boolean;
  host?: "electron" | "web" | "mock";
  message: string;
  details?: string[];
  actionableCommand?: string | null;
  /** Set when the manifest declares supportedArches and host arch isn't in it. */
  archIncompatible?: boolean;
  hostArch?: string;
  supportedArches?: string[];
};

export type HosakaAppCapabilities = {
  host: "electron" | "web";
  platform: string;
  /** CPU arch in flatpak vocabulary: x86_64, aarch64, arm, i386, unknown. */
  arch?: string;
  flatpakAvailable: boolean;
  flathubConfigured?: boolean;
  manifestsRoot?: string;
  manifestsFound?: number;
  mocked: boolean;
  note: string | null;
};

export type FlathubHit = {
  id: string;
  name: string;
  summary: string;
  icon: string | null;
  categories: string[];
};

export type FlathubSearchResponse = {
  ok: boolean;
  query?: string;
  hits: FlathubHit[];
  message?: string;
};

export type StageManifestPayload = {
  flatpak_id: string;
  name?: string;
  id?: string;
  category?: string;
  description?: string;
  provider?: string;
  overwrite?: boolean;
};

export type StageManifestResponse = {
  ok: boolean;
  id?: string;
  path?: string;
  message?: string;
};

type HosakaAppHostBridge = {
  getStatus: (appId: string) => Promise<HosakaAppHostResponse>;
  installApp: (appId: string) => Promise<HosakaAppHostResponse>;
  launchApp: (appId: string) => Promise<HosakaAppHostResponse>;
  listManifests?: () => Promise<unknown[]>;
  capabilities?: () => Promise<HosakaAppCapabilities>;
  flathubSearch?: (query: string) => Promise<FlathubSearchResponse>;
  flathubMeta?: (flatpakId: string) => Promise<{ ok: boolean; id?: string; meta?: unknown; message?: string }>;
  stageManifest?: (payload: StageManifestPayload) => Promise<StageManifestResponse>;
};

declare global {
  interface Window {
    hosakaAppHost?: HosakaAppHostBridge;
  }
}

const HTTP_BASE = "/api/v1/apps";

function bridge(): HosakaAppHostBridge | null {
  return typeof window !== "undefined" && window.hosakaAppHost ? window.hosakaAppHost : null;
}

async function httpJson<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(path, { credentials: "same-origin", ...init });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function unsupported(appId: string, verb: string): HosakaAppHostResponse {
  return {
    ok: false,
    appId,
    manifestFound: Boolean(getHosakaAppById(appId)),
    host: "web",
    message: `apps are disabled in the browser preview — open Hosaka in the Electron kiosk on a Linux host to ${verb} flatpak apps.`,
    actionableCommand: "./scripts/hosaka dev --electron",
  };
}

export async function getHosakaAppCapabilities(): Promise<HosakaAppCapabilities> {
  const b = bridge();
  if (b?.capabilities) return b.capabilities();
  const http = await httpJson<HosakaAppCapabilities>(`${HTTP_BASE}/capabilities`);
  if (http) return http;
  return {
    host: "web",
    platform: typeof navigator !== "undefined" ? navigator.platform : "unknown",
    flatpakAvailable: false,
    mocked: false,
    note: "running in browser preview — flatpak install/launch are unavailable.",
  };
}

export async function refreshHosakaAppsFromHost(): Promise<void> {
  const b = bridge();
  if (b?.listManifests) {
    try {
      const list = await b.listManifests();
      if (Array.isArray(list)) refreshHosakaApps(list);
    } catch { /* keep build-time seed */ }
    return;
  }
  const http = await httpJson<{ apps?: unknown[] }>(`${HTTP_BASE}/`);
  if (http?.apps && Array.isArray(http.apps)) {
    refreshHosakaApps(http.apps);
  }
}

export async function getHosakaAppStatus(raw: string): Promise<HosakaAppHostResponse> {
  const appId = resolveHosakaAppId(raw);
  if (!appId) {
    return { ok: false, manifestFound: false, message: `app not found: ${raw}` };
  }
  const b = bridge();
  if (b) return b.getStatus(appId);
  const http = await httpJson<HosakaAppHostResponse>(`${HTTP_BASE}/${encodeURIComponent(appId)}/status`);
  return http ?? unsupported(appId, "inspect");
}

export async function installHosakaApp(raw: string): Promise<HosakaAppHostResponse> {
  const appId = resolveHosakaAppId(raw);
  if (!appId) {
    return { ok: false, manifestFound: false, message: `app not found: ${raw}` };
  }
  const b = bridge();
  if (b) return b.installApp(appId);
  const http = await httpJson<HosakaAppHostResponse>(
    `${HTTP_BASE}/${encodeURIComponent(appId)}/install`,
    { method: "POST" },
  );
  return http ?? unsupported(appId, "install");
}

export async function launchHosakaApp(raw: string): Promise<HosakaAppHostResponse> {
  const appId = resolveHosakaAppId(raw);
  if (!appId) {
    return { ok: false, manifestFound: false, message: `app not found: ${raw}` };
  }
  const b = bridge();
  if (b) return b.launchApp(appId);
  const http = await httpJson<HosakaAppHostResponse>(
    `${HTTP_BASE}/${encodeURIComponent(appId)}/launch`,
    { method: "POST" },
  );
  return http ?? unsupported(appId, "launch");
}

export async function searchFlathub(query: string): Promise<FlathubSearchResponse> {
  const q = query.trim();
  if (!q) return { ok: false, hits: [], message: "empty query" };
  const b = bridge();
  if (b?.flathubSearch) return b.flathubSearch(q);
  // Browser fallback: hit Flathub directly. CORS is permissive on /api/v2.
  try {
    const res = await fetch(`https://flathub.org/api/v2/search/${encodeURIComponent(q)}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return { ok: false, hits: [], message: `http ${res.status}` };
    const data = (await res.json()) as { hits?: unknown[] } | unknown[];
    const rows: unknown[] = Array.isArray((data as { hits?: unknown[] })?.hits)
      ? ((data as { hits: unknown[] }).hits)
      : Array.isArray(data) ? (data as unknown[]) : [];
    const hits: FlathubHit[] = rows.slice(0, 25).map((rawRow) => {
      const row = rawRow as Record<string, unknown>;
      return {
        id: String(row.app_id ?? row.id ?? ""),
        name: String(row.name ?? row.title ?? ""),
        summary: String(row.summary ?? row.description ?? ""),
        icon: typeof row.icon === "string" ? (row.icon as string) : null,
        categories: Array.isArray(row.categories) ? (row.categories as unknown[]).map(String) : [],
      };
    }).filter((h) => h.id);
    return { ok: true, query: q, hits };
  } catch (error) {
    return { ok: false, hits: [], message: String((error as Error)?.message ?? error) };
  }
}

export async function stageHosakaAppManifest(
  payload: StageManifestPayload,
): Promise<StageManifestResponse> {
  const b = bridge();
  if (b?.stageManifest) {
    const result = await b.stageManifest(payload);
    if (result.ok) await refreshHosakaAppsFromHost();
    return result;
  }
  const http = await httpJson<StageManifestResponse>(`${HTTP_BASE}/stage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (http?.ok) await refreshHosakaAppsFromHost();
  return http ?? {
    ok: false,
    message: "staging is only available in the Electron kiosk on a Linux host.",
  };
}
