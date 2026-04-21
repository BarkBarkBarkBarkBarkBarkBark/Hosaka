// In-house i18n shim — replaces i18next + react-i18next + i18next-http-backend
// + i18next-browser-languagedetector. We were paying ~2 MB of node_modules for
// what amounts to "look up a key in a nested JSON object", so this file is the
// entire i18n surface area now.
//
// Surface intentionally mirrors what the rest of the app already uses:
//   import i18next from "./i18n";
//     i18next.t(key, { ns, returnObjects, ...interp })
//     i18next.language
//     i18next.changeLanguage(code)
//
//   import { useTranslation } from "./i18n";
//     const { t, i18n } = useTranslation("ui");
//     t(key, defaultValue)
//     t(key, { returnObjects: true })
//     t(key, { someInterpolationKey: "value" })
//
// Locale JSON ships *per-language* as its own Vite chunk (import.meta.glob,
// non-eager). At boot we synchronously inline en/* (fallback + most common
// operator language) and asynchronously load the detected language if it
// differs. Total bundled-at-boot JSON is ~20 KB; the other 5 languages are
// fetched only if the operator flips to them — a real win on Pi 3B.

import { useSyncExternalStore } from "react";

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };
type Bundle = Record<string, Json>;
type Bundles = Record<string, Bundle>; // ns -> bundle
type Catalogs = Record<string, Bundles>; // lang -> ns -> bundle

const SUPPORTED = ["en", "es", "fr", "it", "ja", "pt"] as const;
const FALLBACK_LANG = "en";
const STORAGE_KEY = "hosaka.lang";

// Fallback language: inlined into the entry bundle so first paint never waits
// on a fetch. `eager + query:'?url'` would give us URLs; we want the parsed
// JSON object directly, so we use `eager:true` only for en.
const enModules = import.meta.glob("./locales/en/*.json", {
  eager: true,
  import: "default",
}) as Record<string, Bundle>;

// Other languages: lazy-loaded on demand. Vite code-splits one chunk per
// language × namespace, which the operator only pays for if they change lang.
// We deliberately exclude en — it's already in the eager bundle above and
// including it here would fight with rollup over which chunk owns it.
const lazyModules = import.meta.glob("./locales/!(en)/*.json", {
  import: "default",
}) as Record<string, () => Promise<Bundle>>;

const catalogs: Catalogs = {};

function ingest(path: string, bundle: Bundle) {
  // path looks like "./locales/en/ui.json"
  const m = path.match(/\/locales\/([^/]+)\/([^/]+)\.json$/);
  if (!m) return;
  const [, lang, ns] = m;
  catalogs[lang] ??= {};
  catalogs[lang][ns] = bundle;
}

for (const [path, mod] of Object.entries(enModules)) ingest(path, mod);

async function loadLang(lang: string): Promise<void> {
  if (catalogs[lang]) return; // already resident
  const jobs: Promise<void>[] = [];
  for (const [path, loader] of Object.entries(lazyModules)) {
    if (!path.includes(`/locales/${lang}/`)) continue;
    jobs.push(
      loader()
        .then((bundle) => ingest(path, bundle))
        .catch(() => {
          // leave the ns missing; lookup() falls back to en
        }),
    );
  }
  await Promise.all(jobs);
}

function detectInitialLang(): string {
  if (typeof window === "undefined") return FALLBACK_LANG;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED.includes(stored as (typeof SUPPORTED)[number])) {
      return stored;
    }
  } catch {
    // localStorage may be blocked; fall through to navigator detection.
  }
  const nav = (window.navigator?.language || FALLBACK_LANG).split("-")[0];
  return SUPPORTED.includes(nav as (typeof SUPPORTED)[number]) ? nav : FALLBACK_LANG;
}

let currentLang = detectInitialLang();
const listeners = new Set<() => void>();

function notify() {
  for (const l of listeners) l();
}

// Kick off the async load for the detected language if it isn't already in
// the fallback bundle. We don't block on it — lookup() falls through to en
// until the chunk lands, then notify() re-renders consumers.
if (currentLang !== FALLBACK_LANG) {
  void loadLang(currentLang).then(notify);
}

function getNested(bundle: Bundle | undefined, key: string): Json | undefined {
  if (!bundle) return undefined;
  const parts = key.split(".");
  let cur: Json | undefined = bundle;
  for (const p of parts) {
    if (cur && typeof cur === "object" && !Array.isArray(cur) && p in cur) {
      cur = (cur as { [k: string]: Json })[p];
    } else {
      return undefined;
    }
  }
  return cur;
}

function lookup(lang: string, ns: string, key: string): Json | undefined {
  const direct = getNested(catalogs[lang]?.[ns], key);
  if (direct !== undefined) return direct;
  if (lang !== FALLBACK_LANG) {
    return getNested(catalogs[FALLBACK_LANG]?.[ns], key);
  }
  return undefined;
}

function interpolate(template: string, vars: Record<string, unknown>): string {
  return template.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, k: string) => {
    const v = vars[k];
    return v === undefined || v === null ? "" : String(v);
  });
}

export type TFunction = {
  (key: string): string;
  (key: string, defaultValue: string): string;
  (key: string, opts: { returnObjects: true; ns?: string } & Record<string, unknown>): unknown;
  (key: string, opts: { ns?: string } & Record<string, unknown>): string;
};

function makeT(defaultNs: string): TFunction {
  function t(key: string, opts?: string | Record<string, unknown>): unknown {
    const ns = (typeof opts === "object" && opts && typeof opts.ns === "string"
      ? opts.ns
      : defaultNs) as string;
    const value = lookup(currentLang, ns, key);
    const wantObjects =
      typeof opts === "object" && opts !== null && opts.returnObjects === true;

    if (value === undefined) {
      if (typeof opts === "string") return opts;
      return key;
    }

    if (wantObjects) return value;

    if (typeof value === "string") {
      if (typeof opts === "object" && opts) {
        return interpolate(value, opts as Record<string, unknown>);
      }
      return value;
    }

    return key;
  }
  return t as TFunction;
}

// ── public ─────────────────────────────────────────────────────────────────

export type I18n = {
  language: string;
  languages: readonly string[];
  changeLanguage: (lang: string) => Promise<void>;
  t: TFunction;
  on: (event: "languageChanged", cb: (lang: string) => void) => void;
  off: (event: "languageChanged", cb: (lang: string) => void) => void;
};

const eventBus = new Map<string, Set<(arg: string) => void>>();

const i18n: I18n = {
  get language() {
    return currentLang;
  },
  languages: SUPPORTED,
  async changeLanguage(lang: string) {
    if (!SUPPORTED.includes(lang as (typeof SUPPORTED)[number])) return;
    await loadLang(lang);
    currentLang = lang;
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // localStorage blocked: still update in-memory.
    }
    eventBus.get("languageChanged")?.forEach((cb) => cb(lang));
    notify();
  },
  t: makeT("ui"),
  on(event, cb) {
    let bucket = eventBus.get(event);
    if (!bucket) {
      bucket = new Set();
      eventBus.set(event, bucket);
    }
    bucket.add(cb as (arg: string) => void);
  },
  off(event, cb) {
    eventBus.get(event)?.delete(cb as (arg: string) => void);
  },
};

export default i18n;

export function useTranslation(ns: string = "ui"): { t: TFunction; i18n: I18n } {
  // Re-render any consuming component when the language (or its bundle) changes.
  useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => currentLang,
    () => currentLang,
  );
  return { t: makeT(ns), i18n };
}
