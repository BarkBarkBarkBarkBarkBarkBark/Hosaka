import { parse } from "yaml";
import registryRaw from "../../../hosaka-apps/registry.yaml?raw";

const appManifestModules = import.meta.glob("../../../hosaka-apps/apps/*.{yaml,yml}", {
  eager: true,
  query: "?raw",
  import: "default",
}) as Record<string, string>;

export type HosakaAppManifest = {
  id: string;
  name: string;
  category: string;
  description: string;
  provider: string;
  backend: "flatpak" | string;
  flatpak_id: string;
  install: { command: string[] };
  launch: { command: string[] };
  aliases: string[];
  memory: { profile: string; warning?: string };
  permissions_notes: string[];
  account_login_required: boolean;
  hosaka_manages_credentials: boolean;
  notes?: string[];
};

export type HosakaAppsRegistry = {
  version: number;
  registry: {
    id: string;
    name: string;
    description: string;
  };
  policy?: {
    expose_backend_to_user?: boolean;
    require_manifest_for_install?: boolean;
    require_manifest_for_launch?: boolean;
    allow_arbitrary_commands?: boolean;
    store_third_party_credentials?: boolean;
  };
  backends?: {
    flatpak?: {
      remote?: {
        name?: string;
        url?: string;
      };
    };
  };
  apps_dir?: string;
  apps: HosakaAppManifest[];
};

function normalizeAppToken(raw: string): string {
  return raw.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-");
}

function parseManifest<T>(raw: string): T {
  return parse(raw) as T;
}

function toManifest(value: unknown): HosakaAppManifest | null {
  if (!value || typeof value !== "object") return null;
  const data = value as Partial<HosakaAppManifest>;
  const id = typeof data.id === "string" ? normalizeAppToken(data.id) : "";
  if (!id) return null;
  const aliases = Array.isArray(data.aliases)
    ? data.aliases.map((alias) => normalizeAppToken(String(alias))).filter(Boolean)
    : [];
  const installCommand = Array.isArray(data.install?.command)
    ? data.install.command.map((token) => String(token))
    : [];
  const launchCommand = Array.isArray(data.launch?.command)
    ? data.launch.command.map((token) => String(token))
    : [];
  return {
    id,
    name: String(data.name ?? id),
    category: String(data.category ?? "other"),
    description: String(data.description ?? ""),
    provider: String(data.provider ?? "unknown"),
    backend: String(data.backend ?? "flatpak"),
    flatpak_id: String(data.flatpak_id ?? ""),
    install: { command: installCommand },
    launch: { command: launchCommand },
    aliases: Array.from(new Set([id, ...aliases])),
    memory: {
      profile: String(data.memory?.profile ?? "unknown"),
      warning: data.memory?.warning ? String(data.memory.warning) : undefined,
    },
    permissions_notes: Array.isArray(data.permissions_notes)
      ? data.permissions_notes.map((note) => String(note))
      : [],
    account_login_required: Boolean(data.account_login_required),
    hosaka_manages_credentials: Boolean(data.hosaka_manages_credentials),
    notes: Array.isArray(data.notes) ? data.notes.map((note) => String(note)) : [],
  };
}

function loadRegistry(): HosakaAppsRegistry {
  const base = parseManifest<Omit<HosakaAppsRegistry, "apps">>(registryRaw);
  const apps = Object.values(appManifestModules)
    .map((raw) => toManifest(parseManifest<unknown>(raw)))
    .filter((entry): entry is HosakaAppManifest => Boolean(entry))
    .sort((a, b) => a.name.localeCompare(b.name));
  return {
    version: Number(base.version ?? 1),
    registry: {
      id: String(base.registry?.id ?? "hosaka-apps"),
      name: String(base.registry?.name ?? "Hosaka Apps"),
      description: String(base.registry?.description ?? "Hosaka app wrappers."),
    },
    policy: base.policy,
    backends: base.backends,
    apps_dir: typeof base.apps_dir === "string" ? base.apps_dir : "apps",
    apps,
  };
}

export const HOSAKA_APPS_REGISTRY = loadRegistry();
export let HOSAKA_APPS = HOSAKA_APPS_REGISTRY.apps;

let APP_MAP = new Map(HOSAKA_APPS.map((app) => [app.id, app] as const));
const ALIAS_MAP = new Map<string, string>();
function rebuildAliasMap(): void {
  ALIAS_MAP.clear();
  for (const app of HOSAKA_APPS) {
    for (const alias of app.aliases) {
      ALIAS_MAP.set(alias, app.id);
    }
  }
}
rebuildAliasMap();

/**
 * Replace the in-memory manifest set with one fetched from the Electron
 * host (or any other runtime source). The build-time Vite glob is only a
 * seed — staged user manifests appear here without a rebuild.
 */
export function refreshHosakaApps(next: HosakaAppManifest[] | unknown[]): HosakaAppManifest[] {
  const normalized = next
    .map((entry) => toManifest(entry))
    .filter((entry): entry is HosakaAppManifest => Boolean(entry))
    .sort((a, b) => a.name.localeCompare(b.name));
  HOSAKA_APPS = normalized;
  HOSAKA_APPS_REGISTRY.apps = normalized;
  APP_MAP = new Map(normalized.map((app) => [app.id, app] as const));
  rebuildAliasMap();
  try {
    window.dispatchEvent(new CustomEvent("hosaka:apps-changed"));
  } catch { /* SSR / non-DOM */ }
  return normalized;
}

export function getHosakaAppById(id: string): HosakaAppManifest | null {
  return APP_MAP.get(normalizeAppToken(id)) ?? null;
}

export function resolveHosakaAppId(raw: string): string | null {
  const token = normalizeAppToken(raw);
  return ALIAS_MAP.get(token) ?? null;
}

export function resolveHosakaApp(raw: string): HosakaAppManifest | null {
  const id = resolveHosakaAppId(raw);
  return id ? getHosakaAppById(id) : null;
}

export function formatHosakaAppCommand(command: string[]): string {
  return command.join(" ");
}
