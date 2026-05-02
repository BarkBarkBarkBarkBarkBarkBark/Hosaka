/**
 * Store abstraction used by useSyncedDoc.
 *
 * Default backend = localStorage (tiny, zero deps, no sync across devices).
 * When startSync() is called (only on the local appliance build, gated by
 * /api/health nodes_enabled), the backend upgrades to the Automerge-backed
 * repo via dynamic import — so the hosted Vercel build never bundles the
 * ~1.2 MB Automerge WASM blob.
 *
 * The two backends present the exact same surface. Components using
 * useSyncedDoc don't care which is live; they just read/update.
 *
 * Note: we deliberately do NOT import idb-keyval here. The hosted build
 * doesn't ship that package; only `repo.ts` (the Automerge backend) uses
 * IndexedDB directly, and App.tsx dynamic-imports repo.ts behind the
 * nodes_enabled flag. Keeping store.ts free of heavy deps means the
 * hosted Vercel bundle tree-shakes cleanly.
 */

export type DocName =
  | "todo"
  | "messages"
  | "ui"
  | "lang"
  | "llm"
  | "windows"
  | "conversation";

export interface Store {
  /** Read current value, returning `initial` if the doc is empty. */
  get<T>(name: DocName, initial: T): T;
  /** Apply an in-place mutator, persist, and notify subscribers. */
  update<T>(name: DocName, initial: T, mutator: (d: T) => void): void;
  /** Subscribe to changes; returns teardown. */
  subscribe(name: DocName, fn: () => void): () => void;
}

type Listener = () => void;

// ── localStorage backend ─────────────────────────────────────────────────────

const LS_KEY = (name: DocName): string => `hosaka.sync.${name}`;

class LocalStore implements Store {
  private cache = new Map<DocName, unknown>();
  private listeners = new Map<DocName, Set<Listener>>();

  get<T>(name: DocName, initial: T): T {
    if (this.cache.has(name)) return this.cache.get(name) as T;
    let value: T = initial;
    try {
      const raw = localStorage.getItem(LS_KEY(name));
      if (raw) value = { ...initial, ...(JSON.parse(raw) as T) };
    } catch {
      // Quota / disabled storage / bad JSON — fall through to initial.
    }
    this.cache.set(name, value);
    return value;
  }

  update<T>(name: DocName, initial: T, mutator: (d: T) => void): void {
    const current = this.get<T>(name, initial);
    // Shallow clone so `===` changes on update (important for React memo);
    // deeper structures get cloned via JSON round-trip on persist, so minor
    // in-place mutations within nested arrays/objects are still captured.
    const next = structuredClone(current);
    mutator(next);
    this.cache.set(name, next);
    try {
      localStorage.setItem(LS_KEY(name), JSON.stringify(next));
    } catch {
      // Quota exceeded / private mode — keep in memory, ignore persistence.
    }
    this.fire(name);
  }

  subscribe(name: DocName, fn: Listener): () => void {
    let set = this.listeners.get(name);
    if (!set) {
      set = new Set();
      this.listeners.set(name, set);
    }
    set.add(fn);
    return () => {
      set?.delete(fn);
    };
  }

  fire(name: DocName): void {
    const set = this.listeners.get(name);
    if (!set) return;
    for (const fn of set) {
      try {
        fn();
      } catch {
        // swallow — broken subscriber shouldn't stop the others
      }
    }
  }
}

// ── active store (swappable) ─────────────────────────────────────────────────

let active: Store = new LocalStore();

export function getStore(): Store {
  return active;
}

/** Install a replacement store (used by repo.ts to upgrade to Automerge).
 *  All existing subscribers are re-notified so components re-read from
 *  the new backend. */
export function installStore(next: Store, previous: LocalStore | null): void {
  active = next;
  // On swap, fire every doc's listeners so they pull the new state.
  if (previous) {
    const ls = previous as unknown as { listeners: Map<DocName, Set<Listener>> };
    for (const [, set] of ls.listeners) {
      for (const fn of set) {
        try {
          fn();
        } catch {}
      }
    }
  }
}

export function getLocalStore(): LocalStore | null {
  return active instanceof LocalStore ? active : null;
}
