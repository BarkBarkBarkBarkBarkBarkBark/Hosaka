/**
 * Automerge-backed Store for the local appliance build.
 *
 * Loaded via dynamic import only when App.tsx learns `nodes_enabled: true`
 * from /api/health. The hosted Vercel build never imports this file and
 * therefore never bundles Automerge's ~1.2 MB WASM payload.
 *
 * Message flow (per node):
 *
 *   Browser tab  <── WebSocket ──>  local Python (/ws/sync)  <── WebSocket ──>  peer Python
 *        ^                                   |                                       |
 *        └──────── fan-out to other ─────────┘   (relays to other peers + own        v
 *                  local browser tabs                                        peer's browser)
 *
 * The local Python is a dumb relay — all CRDT logic lives here. Each
 * WS message is a small JSON envelope around base64-encoded Automerge
 * bytes. `loadIncremental` handles both full saves and concatenated
 * change streams, so snapshots + deltas use the same code path.
 */
import * as A from "@automerge/automerge";
import * as idb from "idb-keyval";
import {
  DocName,
  Store,
  getLocalStore,
  getStore,
  installStore,
} from "./store";

type WireMessage =
  | { type: "hello"; node_id: string; role: "browser" }
  | { type: "snapshot"; doc: DocName; b64: string }
  | { type: "changes"; doc: DocName; b64: string };

type Listener = () => void;

interface Slot<T> {
  doc: A.Doc<T>;
  listeners: Set<Listener>;
  initial: T;
}

class AutomergeStore implements Store {
  slots = new Map<DocName, Slot<unknown>>();

  get<T>(name: DocName, initial: T): T {
    const slot = this.ensureSlotSync<T>(name, initial);
    // toJS gives a plain JS object snapshot React can safely diff.
    return A.toJS(slot.doc) as T;
  }

  update<T>(name: DocName, initial: T, mutator: (d: T) => void): void {
    const slot = this.ensureSlotSync<T>(name, initial);
    const prev = slot.doc;
    const next = A.change(prev, (d) => mutator(d as T));
    if (next === prev) return;

    slot.doc = next;
    this.fire(slot);
    void idb.set(idbKey(name), A.save(next)).catch(() => {});

    const diff = A.getChanges(prev, next);
    if (diff.length > 0) {
      send({ type: "changes", doc: name, b64: b64encode(concatBytes(diff)) });
    }
  }

  subscribe(name: DocName, fn: Listener): () => void {
    // If the slot isn't materialized yet we haven't seen a get/update for
    // it; create an empty slot with `undefined` initial and adopt the real
    // initial on first get. (useSyncedDoc always calls snapshot first so
    // in practice this path is rare.)
    const slot = this.slots.get(name) ?? this.createEmptySlot(name);
    slot.listeners.add(fn);
    return () => {
      slot.listeners.delete(fn);
    };
  }

  fire(slot: Slot<unknown>): void {
    for (const fn of slot.listeners) {
      try { fn(); } catch {}
    }
  }

  // ── internals ──

  private createEmptySlot(name: DocName): Slot<unknown> {
    const slot: Slot<unknown> = {
      doc: A.init<unknown>(),
      listeners: new Set(),
      initial: undefined,
    };
    this.slots.set(name, slot);
    return slot;
  }

  private ensureSlotSync<T>(name: DocName, initial: T): Slot<T> {
    const existing = this.slots.get(name) as Slot<T> | undefined;
    if (existing) return existing;

    const doc = A.change(A.init<T>(), (d) => {
      const target = d as Record<string, unknown>;
      for (const [k, v] of Object.entries(initial as Record<string, unknown>)) {
        if (target[k] === undefined) target[k] = structuredClone(v);
      }
    });

    const slot: Slot<T> = { doc, listeners: new Set(), initial };
    this.slots.set(name, slot as Slot<unknown>);

    // Hydrate asynchronously: prefer the Automerge snapshot stored in
    // IndexedDB, fall back to the legacy localStorage blob (one-shot
    // migration from Phase 1 storage). We don't block synchronously
    // because React's render loop mustn't await.
    void hydrate<T>(name, slot, initial);

    return slot;
  }

  /** Called by the WS onmessage path. Applies incoming changes/snapshot bytes. */
  applyIncoming(name: DocName, bytes: Uint8Array): void {
    const slot = this.slots.get(name);
    if (!slot) {
      // Receive something before we've ever asked for the doc: seed a
      // placeholder slot so the bytes aren't lost. initial=undefined
      // means get() will fail if called before initialSeeded — but we
      // overwrite that on first get().
      const placeholder = this.createEmptySlot(name);
      try {
        placeholder.doc = A.loadIncremental(placeholder.doc, bytes);
      } catch {
        return;
      }
      void idb.set(idbKey(name), A.save(placeholder.doc)).catch(() => {});
      this.fire(placeholder);
      return;
    }
    try {
      slot.doc = A.loadIncremental(slot.doc, bytes);
    } catch {
      return;
    }
    void idb.set(idbKey(name), A.save(slot.doc)).catch(() => {});
    this.fire(slot);
  }

  listDocs(): [DocName, Uint8Array][] {
    const out: [DocName, Uint8Array][] = [];
    for (const [name, slot] of this.slots) {
      out.push([name, A.save(slot.doc)]);
    }
    return out;
  }
}

async function hydrate<T>(name: DocName, slot: Slot<T>, initial: T): Promise<void> {
  try {
    const saved = await idb.get<Uint8Array>(idbKey(name));
    if (saved && saved.byteLength > 0) {
      slot.doc = A.loadIncremental(slot.doc, saved);
      store?.fire(slot as Slot<unknown>);
      return;
    }
  } catch {
    // idb unavailable (Safari private mode) — fall through to legacy JSON.
  }

  // Legacy migration: pre-Phase-2 data was stored as JSON under various
  // localStorage keys. Seed the Automerge doc from there if we find it.
  const legacyKey = LEGACY_KEYS[name];
  if (!legacyKey) return;
  try {
    const raw = localStorage.getItem(legacyKey);
    let imported: unknown = null;
    if (raw) {
      try { imported = JSON.parse(raw); } catch { imported = null; }
    }

    // messages had a secondary config key — fold it into the shape.
    let messagesConfig: unknown = null;
    if (name === "messages") {
      try {
        const rawCfg = localStorage.getItem("hosaka.messages.config.v1");
        if (rawCfg) messagesConfig = JSON.parse(rawCfg);
      } catch {}
    }

    // llm's pre-sync life spanned two keys (gemini + provider). We pull
    // both so a user with history in either one doesn't lose settings.
    let llmProvider: unknown = null;
    if (name === "llm") {
      try {
        const rawProv = localStorage.getItem("hosaka.llm-provider.v1");
        if (rawProv) llmProvider = JSON.parse(rawProv);
      } catch {}
    }

    if (imported === null && messagesConfig === null && llmProvider === null) return;

    slot.doc = A.change(slot.doc, (d) => {
      applyLegacy(d as Record<string, unknown>, name, imported, initial);
      if (name === "messages" && messagesConfig && typeof messagesConfig === "object") {
        (d as Record<string, unknown>).config = messagesConfig;
      }
      if (name === "llm" && llmProvider && typeof llmProvider === "object") {
        for (const [k, v] of Object.entries(llmProvider)) {
          (d as Record<string, unknown>)[k] = v;
        }
      }
    });
    void idb.set(idbKey(name), A.save(slot.doc)).catch(() => {});
    store?.fire(slot as Slot<unknown>);
  } catch {
    // Bad JSON; leave initial as-is.
  }
}

// Mapping from our synced-doc name → the legacy localStorage key used in
// the pre-sync world. Kept for exactly one major release for rollback
// safety; we DO NOT delete the old key after migrating.
const LEGACY_KEYS: Partial<Record<DocName, string>> = {
  todo: "hosaka.todo.v1",
  messages: "hosaka.messages.v1",
  ui: "hosaka.ui.v1",
  lang: "hosaka.lang",
  llm: "hosaka.llm.v1",
  windows: "hosaka.windows.v1",
  conversation: "hosaka.conversation.v1",
};

function applyLegacy<T>(
  dest: Record<string, unknown>,
  name: DocName,
  imported: unknown,
  _initial: T,
): void {
  // Each legacy blob has a different shape; map them into the synced shape.
  switch (name) {
    case "todo": {
      if (Array.isArray(imported)) dest.items = imported;
      return;
    }
    case "messages": {
      if (Array.isArray(imported)) dest.entries = imported;
      return;
    }
    case "ui":
    case "llm": {
      if (imported && typeof imported === "object") {
        for (const [k, v] of Object.entries(imported)) dest[k] = v;
      }
      return;
    }
    case "windows":
    case "conversation": {
      if (imported && typeof imported === "object") {
        for (const [k, v] of Object.entries(imported)) dest[k] = v;
      }
      return;
    }
    case "lang": {
      if (typeof imported === "string") dest.code = imported;
      return;
    }
  }
}

// ── module singleton ────────────────────────────────────────────────────────

const NODE_ID = Math.random().toString(36).slice(2, 10);
const idbKey = (name: DocName): string => `hosaka.sync.idb.${name}`;

let store: AutomergeStore | null = null;
let ws: WebSocket | null = null;
let wsReady = false;
let reconnectDelay = 500;
const outbox: WireMessage[] = [];

// ── public API ──────────────────────────────────────────────────────────────

/**
 * Promote the default localStorage Store to this Automerge-backed one
 * and open the WS to the local Python relay. Idempotent.
 */
export function startSync(): void {
  if (store) {
    if (!ws) connect();
    return;
  }
  const next = new AutomergeStore();
  store = next;

  // Install the Automerge store as active. Any existing components that
  // already mounted against the LocalStore will be notified and re-read
  // through the new backend. The AutomergeStore lazily hydrates each doc
  // from IndexedDB (Automerge bytes) or, failing that, the legacy
  // localStorage key (JSON) on first access.
  installStore(next, getLocalStore());

  // Expose a read-only handle for non-React code (the xterm shell's
  // `/todo list` command reads through this).
  if (typeof window !== "undefined") {
    (window as unknown as { __hosakaRepo?: unknown }).__hosakaRepo = {
      getDoc: <T,>(name: DocName): T | null => {
        return getStore().get<T>(name, {} as T);
      },
    };
  }
  connect();
}

export function getAutomergeStore(): AutomergeStore | null {
  return store;
}

// ── WebSocket transport ─────────────────────────────────────────────────────

function connect(): void {
  if (ws) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/sync`;

  let socket: WebSocket;
  try {
    socket = new WebSocket(url);
  } catch {
    scheduleReconnect();
    return;
  }

  ws = socket;

  socket.onopen = () => {
    wsReady = true;
    reconnectDelay = 500;
    socket.send(JSON.stringify({ type: "hello", node_id: NODE_ID, role: "browser" }));
    // Send snapshots of every doc we already know about so the relay can
    // propagate to new peers that have never seen them.
    if (store) {
      for (const [name, bytes] of store.listDocs()) {
        socket.send(
          JSON.stringify({ type: "snapshot", doc: name, b64: b64encode(bytes) }),
        );
      }
    }
    while (outbox.length > 0) {
      const m = outbox.shift();
      if (m) socket.send(JSON.stringify(m));
    }
  };

  socket.onmessage = (ev) => {
    let msg: WireMessage;
    try {
      msg = JSON.parse(typeof ev.data === "string" ? ev.data : new TextDecoder().decode(ev.data));
    } catch {
      return;
    }
    if (msg.type === "hello") return;
    if (!store) return;
    const bytes = b64decode(msg.b64);
    store.applyIncoming(msg.doc, bytes);
  };

  socket.onclose = () => {
    wsReady = false;
    ws = null;
    scheduleReconnect();
  };
  socket.onerror = () => {
    try { socket.close(); } catch {}
  };
}

function scheduleReconnect(): void {
  const delay = Math.min(reconnectDelay, 15000);
  reconnectDelay = Math.min(reconnectDelay * 2, 15000);
  setTimeout(connect, delay);
}

function send(msg: WireMessage): void {
  if (ws && wsReady) {
    try {
      ws.send(JSON.stringify(msg));
      return;
    } catch {
      // Fall through to outbox.
    }
  }
  outbox.push(msg);
  if (outbox.length > 500) outbox.splice(0, outbox.length - 500);
}

// ── helpers ─────────────────────────────────────────────────────────────────

function concatBytes(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.byteLength, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.byteLength;
  }
  return out;
}

function b64encode(bytes: Uint8Array): string {
  // Chunked to avoid the ~100 KB String.fromCharCode stack-size limit.
  let out = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    out += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(out);
}

function b64decode(s: string): Uint8Array {
  const raw = atob(s);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}
