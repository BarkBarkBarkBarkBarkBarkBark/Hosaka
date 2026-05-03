// Websocket client for the hosaka agent-server (picoclaw backend).
//
// Contract is tiny and deliberately boring:
//   client → { message: "..." }
//   server → { type: "hello"   | "thinking" | "reply" | "error", ... }
//
// We keep exactly one connection + one in-flight request at a time.
// If the server TTL reaps us, the next send reopens the socket.

export type AgentConfig = {
  url: string;       // e.g. wss://hosaka-agent.fly.dev/ws/agent
  passphrase: string;
  enabled: boolean;
};

// Split storage:
//   - URL + enabled flag → synced doc ("llm" doc, agent.* sub-keys). Safe
//     to share across devices — it's where your agent lives, not a secret.
//   - Passphrase → LOCAL-ONLY plain localStorage. The passphrase is a
//     shared secret for the Fly.io-hosted agent; treating it as sensitive
//     and per-device is the conservative choice until Phase 4 adds
//     passphrase-derived encryption for synced LLM docs.
const PASSPHRASE_KEY = "hosaka.agent.passphrase";
// Legacy composite key used pre-sync; read-only fallback for one release.
const LEGACY_STORAGE_KEY = "hosaka.agent.v2";
const HOSTED_AGENT_URL = "wss://hosaka-field-terminal-alpha.fly.dev/ws/agent";

function sameOriginAgentUrl(): string {
  if (typeof window === "undefined") return "ws://127.0.0.1:8421/ws/agent";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/agent`;
}

// Baked-in default so users don't have to paste the URL. Local/appliance builds
// use the same origin backend (`/ws/agent`, proxied by Vite in dev). Hosted gated
// builds still default to the Fly relay unless VITE_HOSAKA_AGENT_URL overrides it.
export const DEFAULT_AGENT_URL: string =
  (import.meta.env.VITE_HOSAKA_AGENT_URL as string | undefined) ??
  ((import.meta.env.VITE_HOSAKA_GATED as string | undefined) === "1"
    ? HOSTED_AGENT_URL
    : sameOriginAgentUrl());

// Whether the hosted build starts with the agent channel locked. The client
// deliberately does NOT know the password — that's the point. Users type a
// candidate, we ship it to the server as `?token=…`, the server decides.
// Appliance builds (VITE_HOSAKA_GATED unset or 0) boot with the channel open.
export const GATED: boolean =
  (import.meta.env.VITE_HOSAKA_GATED as string | undefined) === "1";

export const DEFAULT_AGENT_CONFIG: AgentConfig = {
  url: DEFAULT_AGENT_URL,
  passphrase: "",
  enabled: !GATED,
};

export function loadAgentConfig(): AgentConfig {
  // Appliance builds (!GATED) always boot with the channel open.
  // Hosted builds require the user to say the word out loud; once the
  // server validates it we persist enabled=true so it survives navigation
  // within the tab, but it resets on a fresh session / cleared storage.

  // Shared fields (url, enabled) from the synced llm doc.
  let url = DEFAULT_AGENT_CONFIG.url;
  let enabled = DEFAULT_AGENT_CONFIG.enabled;
  try {
    // Lazy-import store to avoid a circular dep at module load.
    const raw = getStore().get<AgentStoreFields>("llm", {});
    if (raw.agent_url) url = raw.agent_url;
    if (GATED && typeof raw.agent_enabled === "boolean") enabled = raw.agent_enabled;
  } catch {
    // Fall through to defaults.
  }

  // Passphrase: local-only. Separate storage key = won't leak to peers.
  let passphrase = "";
  try {
    const p = localStorage.getItem(PASSPHRASE_KEY);
    if (p) passphrase = p;
  } catch {
    // storage blocked
  }

  // One-shot migration from the pre-sync composite key. We read and
  // forward to the new locations, but intentionally keep the legacy key
  // around for one release so a rollback doesn't lose the operator's URL.
  if (url === DEFAULT_AGENT_CONFIG.url && !passphrase) {
    try {
      const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (raw) {
        const stored = JSON.parse(raw) as Partial<AgentConfig>;
        if (stored.url) url = stored.url;
        if (stored.passphrase) {
          passphrase = stored.passphrase;
          try { localStorage.setItem(PASSPHRASE_KEY, stored.passphrase); } catch {}
        }
        if (GATED && typeof stored.enabled === "boolean") enabled = stored.enabled;
      }
    } catch {}
  }

  if (!GATED && url === HOSTED_AGENT_URL) {
    url = sameOriginAgentUrl();
    passphrase = "";
  }

  return { url, passphrase, enabled };
}

export function localAgentConfig(): AgentConfig {
  return { url: sameOriginAgentUrl(), passphrase: "", enabled: true };
}

type AgentStoreFields = {
  agent_url?: string;
  agent_enabled?: boolean;
};

// Avoid an import cycle by deferring the import of sync/store to the
// function call site. Vite hoists this to a module-level import in the
// bundle anyway, but keeping the declaration here documents intent.
import { getStore } from "../sync/store";

// Try to unlock the channel by opening a probe WebSocket with `candidate` as
// the token. Resolves `{ ok: true }` if the server sends the `hello` frame
// (token accepted). Resolves `{ ok: false, code }` if the server closes with
// 4401 unauthorized, or if the socket errors for any other reason. Used by
// the shell's "speak the word" unlock flow — the client never has to know
// the actual passphrase, because the server decides.
export async function attemptUnlock(
  url: string,
  candidate: string,
  timeoutMs = 4000,
): Promise<{ ok: true } | { ok: false; code: AgentErrorCode }> {
  if (!looksLikeWsUrl(url)) return { ok: false, code: "not_configured" };
  if (!candidate) return { ok: false, code: "unauthorized" };

  return new Promise((resolve) => {
    let ws: WebSocket;
    try {
      const u = new URL(url);
      u.searchParams.set("token", candidate);
      ws = new WebSocket(u.toString());
    } catch {
      resolve({ ok: false, code: "unreachable" });
      return;
    }

    let settled = false;
    let sawClose = false;
    const done = (r: { ok: true } | { ok: false; code: AgentErrorCode }) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      try { ws.close(); } catch { /* already closing */ }
      resolve(r);
    };
    const timer = window.setTimeout(() => done({ ok: false, code: "timeout" }), timeoutMs);

    ws.addEventListener("message", (evt) => {
      try {
        const data = JSON.parse(evt.data) as AgentEvent;
        if (data.type === "hello") done({ ok: true });
      } catch { /* ignore */ }
    });
    ws.addEventListener("close", (evt) => {
      sawClose = true;
      // Server closes 4401 on bad token — that's our signal to say "not the word".
      if (evt.code === 4401) done({ ok: false, code: "unauthorized" });
      else done({ ok: false, code: "dropped" });
    });
    ws.addEventListener("error", () => {
      done({ ok: false, code: sawClose ? "unauthorized" : "unreachable" });
    });
  });
}

export function saveAgentConfig(cfg: AgentConfig): void {
  // Synced (non-sensitive) bits go to the shared llm doc.
  try {
    getStore().update<AgentStoreFields>("llm", {}, (d) => {
      d.agent_url = cfg.url;
      if (GATED) d.agent_enabled = cfg.enabled;
    });
  } catch {
    // store unavailable; fall through so we at least persist the passphrase.
  }

  // Passphrase stays device-local.
  try {
    if (cfg.passphrase) {
      localStorage.setItem(PASSPHRASE_KEY, cfg.passphrase);
    } else {
      localStorage.removeItem(PASSPHRASE_KEY);
    }
  } catch {
    // storage blocked: in-memory copy will still work for this session.
  }
}

export type AgentHello = {
  type: "hello";
  sid: string;
  picoclaw: boolean;
  model: string | null;
  ttl_seconds: number;
};

export type ShellResult =
  | { ok: true; stdout: string; stderr: string; exit: number }
  | { ok: false; code: AgentErrorCode };

export type AgentEvent =
  | AgentHello
  | { type: "thinking" }
  | { type: "ping" }
  | { type: "reply"; text?: string; stdout: string; stderr: string }
  | { type: "shell_reply"; stdout: string; stderr: string; exit: number }
  | { type: "error"; error: string };

export type AgentErrorCode =
  | "not_configured"
  | "unauthorized"
  | "unreachable"
  | "timeout"
  | "rate_limited"
  | "empty"
  | "busy"
  | "dropped"
  | "unknown";

export type AgentResult =
  | { ok: true; text: string; sid: string; model: string | null }
  | { ok: false; code: AgentErrorCode };

function buildWsUrl(cfg: AgentConfig): string {
  const u = new URL(cfg.url);
  if (cfg.passphrase) {
    u.searchParams.set("token", cfg.passphrase);
  } else {
    u.searchParams.delete("token");
  }
  return u.toString();
}

function looksLikeWsUrl(url: string): boolean {
  return /^wss?:\/\//i.test(url);
}

export class AgentClient {
  private ws: WebSocket | null = null;
  private hello: AgentHello | null = null;
  private inflight: {
    resolve: (r: AgentResult) => void;
    timer: number;
  } | null = null;
  private shellInflight: {
    resolve: (r: ShellResult) => void;
    timer: number;
  } | null = null;

  constructor(private cfg: AgentConfig) {}

  updateConfig(cfg: AgentConfig): void {
    if (this.sameConfig(cfg)) return;
    this.cfg = cfg;
    this.close();
  }

  private sameConfig(next: AgentConfig): boolean {
    return this.cfg.url === next.url
      && this.cfg.passphrase === next.passphrase
      && this.cfg.enabled === next.enabled;
  }

  private async ensureOpen(): Promise<AgentErrorCode | null> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return null;
    if (!looksLikeWsUrl(this.cfg.url)) {
      return "not_configured";
    }

    return new Promise<AgentErrorCode | null>((resolve) => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(buildWsUrl(this.cfg));
      } catch {
        resolve("unreachable");
        return;
      }
      this.ws = ws;
      let settled = false;
      let sawClose = false;

      const cleanup = () => {
        window.clearTimeout(helloTimer);
        ws.removeEventListener("open", onOpen);
        ws.removeEventListener("error", onError);
      };

      const helloTimer = window.setTimeout(() => {
        if (!settled) {
          settled = true;
          cleanup();
          try { ws.close(); } catch { /* noop */ }
          resolve("timeout");
        }
      }, 4000);

      const onOpen = () => {
        // Wait for the "hello" frame before considering the channel ready.
      };
      const onError = () => {
        if (!settled) {
          settled = true;
          cleanup();
          resolve(sawClose ? "unauthorized" : "unreachable");
        }
      };

      ws.addEventListener("open", onOpen);
      ws.addEventListener("error", onError);

      ws.addEventListener("message", (evt) => {
        let data: AgentEvent | null = null;
        try {
          data = JSON.parse(evt.data) as AgentEvent;
        } catch {
          return;
        }
        if (!data) return;

        if (data.type === "hello") {
          this.hello = data;
          if (!settled) {
            settled = true;
            cleanup();
            resolve(null);
          }
          return;
        }

        if (data.type === "reply") {
          if (this.inflight) {
            window.clearTimeout(this.inflight.timer);
            // NEVER fall back to raw stdout/stderr — that's where the picoclaw
            // banner and log chrome live. If the server-side cleaner produced
            // nothing usable, treat it as empty and let the shell render a
            // branded placeholder.
            const txt = (data.text ?? "").trim();
            if (!txt) {
              this.inflight.resolve({ ok: false, code: "empty" });
            } else {
              this.inflight.resolve({
                ok: true,
                text: txt,
                sid: this.hello?.sid ?? "?",
                model: this.hello?.model ?? null,
              });
            }
            this.inflight = null;
          }
          return;
        }

        if (data.type === "error") {
          const e = (data.error ?? "").toLowerCase();
          const code: AgentErrorCode = /unauth/.test(e)
            ? "unauthorized"
            : /rate/.test(e)
              ? "rate_limited"
              : /timed out|timeout/.test(e)
                ? "timeout"
                : /still thinking|patience|busy/.test(e)
                  ? "busy"
                  : "unknown";
          if (this.inflight) {
            window.clearTimeout(this.inflight.timer);
            this.inflight.resolve({ ok: false, code });
            this.inflight = null;
          }
          if (this.shellInflight) {
            window.clearTimeout(this.shellInflight.timer);
            this.shellInflight.resolve({ ok: false, code });
            this.shellInflight = null;
          }
          return;
        }

        if (data.type === "shell_reply") {
          if (this.shellInflight) {
            window.clearTimeout(this.shellInflight.timer);
            this.shellInflight.resolve({
              ok: true,
              stdout: (data as AgentEvent & { type: "shell_reply" }).stdout,
              stderr: (data as AgentEvent & { type: "shell_reply" }).stderr,
              exit: (data as AgentEvent & { type: "shell_reply" }).exit,
            });
            this.shellInflight = null;
          }
          return;
        }

        // ping / thinking → no-op (server is just keeping the channel warm)
      });

      ws.addEventListener("close", (evt) => {
        sawClose = true;
        if (!settled) {
          settled = true;
          cleanup();
          // 4401 is the server's "unauthorized" code.
          resolve(evt.code === 4401 ? "unauthorized" : "unreachable");
        }
        if (this.inflight) {
          window.clearTimeout(this.inflight.timer);
          this.inflight.resolve({ ok: false, code: "dropped" });
          this.inflight = null;
        }
        if (this.shellInflight) {
          window.clearTimeout(this.shellInflight.timer);
          this.shellInflight.resolve({ ok: false, code: "dropped" });
          this.shellInflight = null;
        }
        this.hello = null;
        this.ws = null;
      });
    });
  }

  async send(message: string): Promise<AgentResult> {
    if (this.inflight) {
      return { ok: false, code: "busy" };
    }

    const openErr = await this.ensureOpen();
    if (openErr) return { ok: false, code: openErr };

    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return { ok: false, code: "unreachable" };
    }

    return new Promise<AgentResult>((resolve) => {
      const timer = window.setTimeout(() => {
        if (this.inflight) {
          this.inflight = null;
          resolve({ ok: false, code: "timeout" });
        }
      }, 35_000);

      this.inflight = { resolve, timer };
      ws.send(JSON.stringify({ message }));
    });
  }

  async runShell(cmd: string): Promise<ShellResult> {
    if (this.shellInflight) {
      return { ok: false, code: "busy" };
    }
    const openErr = await this.ensureOpen();
    if (openErr) return { ok: false, code: openErr };
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return { ok: false, code: "unreachable" };
    }
    return new Promise<ShellResult>((resolve) => {
      const timer = window.setTimeout(() => {
        if (this.shellInflight) {
          this.shellInflight = null;
          resolve({ ok: false, code: "timeout" });
        }
      }, 15_000);
      this.shellInflight = { resolve, timer };
      ws.send(JSON.stringify({ type: "shell", cmd }));
    });
  }

  close(): void {
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        // ignore
      }
    }
    this.ws = null;
    this.hello = null;
    if (this.inflight) {
      window.clearTimeout(this.inflight.timer);
      this.inflight.resolve({ ok: false, code: "dropped" });
      this.inflight = null;
    }
    if (this.shellInflight) {
      window.clearTimeout(this.shellInflight.timer);
      this.shellInflight.resolve({ ok: false, code: "dropped" });
      this.shellInflight = null;
    }
  }
}

let _singleton: AgentClient | null = null;
export function getAgent(cfg: AgentConfig = loadAgentConfig()): AgentClient {
  if (!_singleton) {
    _singleton = new AgentClient(cfg);
  } else {
    _singleton.updateConfig(cfg);
  }
  return _singleton;
}
