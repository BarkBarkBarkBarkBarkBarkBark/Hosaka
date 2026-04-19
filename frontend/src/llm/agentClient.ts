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

const STORAGE_KEY = "hosaka.agent.v1";

// Baked-in default so users don't have to paste the URL.  Override at build
// time with `VITE_HOSAKA_AGENT_URL=wss://... npm run build` or at runtime in
// the settings drawer.
export const DEFAULT_AGENT_URL: string =
  (import.meta.env.VITE_HOSAKA_AGENT_URL as string | undefined) ??
  "wss://hosaka-field-terminal-alpha.fly.dev/ws/agent";

// The "magic word" a visitor can type in the terminal to auto-configure the
// agent with the default URL + shared passphrase.  Matches server-side
// HOSAKA_ACCESS_TOKEN.  Override at build with VITE_HOSAKA_MAGIC_WORD.
export const MAGIC_WORD: string =
  (import.meta.env.VITE_HOSAKA_MAGIC_WORD as string | undefined) ?? "neuro";

// picoclaw is the heartbeat — but the channel is closed until the visitor
// says the magic word. The url + passphrase are pre-filled so saying neuro
// is the only step required to open the door.
export const DEFAULT_AGENT_CONFIG: AgentConfig = {
  url: DEFAULT_AGENT_URL,
  passphrase: MAGIC_WORD,
  enabled: false,
};

export function loadAgentConfig(): AgentConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_AGENT_CONFIG };
    const stored = JSON.parse(raw) as Partial<AgentConfig>;
    return {
      url: stored.url || DEFAULT_AGENT_CONFIG.url,
      passphrase: stored.passphrase || DEFAULT_AGENT_CONFIG.passphrase,
      enabled: stored.enabled ?? DEFAULT_AGENT_CONFIG.enabled,
    };
  } catch {
    return { ...DEFAULT_AGENT_CONFIG };
  }
}

export function saveAgentConfig(cfg: AgentConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
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
  // Pass the token in the query string as a fallback for browsers that
  // refuse custom headers on websocket upgrades. The server accepts both.
  const u = new URL(cfg.url);
  u.searchParams.set("token", cfg.passphrase);
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
    this.cfg = cfg;
    this.close();
  }

  private async ensureOpen(): Promise<AgentErrorCode | null> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return null;
    if (!looksLikeWsUrl(this.cfg.url) || !this.cfg.passphrase) {
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
        ws.removeEventListener("open", onOpen);
        ws.removeEventListener("error", onError);
      };

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
          if (this.inflight) {
            window.clearTimeout(this.inflight.timer);
            const e = (data.error ?? "").toLowerCase();
            const code: AgentErrorCode = /unauth/.test(e)
              ? "unauthorized"
              : /rate/.test(e)
                ? "rate_limited"
                : /timed out|timeout/.test(e)
                  ? "timeout"
                  : /still thinking|patience/.test(e)
                    ? "busy"
                    : "unknown";
            this.inflight.resolve({ ok: false, code });
            this.inflight = null;
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
      }, 120_000);

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
