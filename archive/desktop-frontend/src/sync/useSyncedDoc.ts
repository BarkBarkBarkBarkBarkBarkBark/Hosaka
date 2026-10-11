/**
 * useSyncedDoc — React hook for a reactive, (optionally-synced) document.
 *
 * Usage:
 *   const [todos, update] = useSyncedDoc<TodoDoc>("todo", { items: [] });
 *   update((d) => d.items.push({ id, text, closed: false }));
 *
 * By default this uses a localStorage-backed Store (no sync, no deps).
 * On the local appliance, App.tsx calls `startSync()` from ./repo when
 * /api/health reports nodes_enabled — that dynamic-imports Automerge,
 * loads the seed from localStorage, and installs itself as the active
 * Store. Components don't need to care which backend is live.
 *
 * The separation exists so the hosted Vercel build never bundles the
 * ~1.2 MB Automerge WASM. Kiosk builds get full CRDT sync; hosted gets
 * local-only persistence.
 */
import { useCallback, useSyncExternalStore } from "react";
import { DocName, getStore } from "./store";

type Updater<T> = (mutator: (d: T) => void) => void;

export function useSyncedDoc<T>(name: DocName, initial: T): [T, Updater<T>] {
  const snapshot = useCallback(
    () => getStore().get<T>(name, initial),
    [name, initial],
  );

  const sub = useCallback(
    (listener: () => void) => getStore().subscribe(name, listener),
    [name],
  );

  const value = useSyncExternalStore(sub, snapshot, snapshot);

  const update: Updater<T> = useCallback(
    (mutator) => {
      getStore().update<T>(name, initial, mutator);
    },
    [name, initial],
  );

  return [value, update];
}
