// Gemini client — proxy-only.
//
// The browser never holds a Gemini API key. Every request goes through the
// Vercel Edge Function at /api/gemini, which injects the server-side
// GEMINI_API_KEY. If the proxy is down or the env var isn't set, we surface
// a typed error so the shell can render branded in-character copy.
//
// NOTE: picoclaw (the agent backend on Fly) is the primary input path for
// free-text. This client is only used by explicit /ask and /chat commands.

export const GEMINI_MODELS = [
  "gemini-2.5-flash-lite",
  "gemini-2.5-flash",
  "gemini-2.0-flash",
  "gemini-2.0-flash-lite",
] as const;

export type GeminiModel = (typeof GEMINI_MODELS)[number];

export type LlmConfig = {
  model: GeminiModel;
};

export type LlmMessage = {
  role: "user" | "assistant";
  text: string;
};

export type LlmResult =
  | { ok: true; text: string; model: string }
  | { ok: false; code: "proxy_down" | "rate_limited" | "empty" | "unknown" };

export const DEFAULT_CONFIG: LlmConfig = {
  model: "gemini-2.5-flash-lite",
};

// Read/write the gemini model preference through the shared sync Store.
// On the appliance this means the preference propagates to peer nodes; on
// the hosted build the LocalStore keeps it in localStorage as before.
// This is purely a model-name preference — NO API key is ever involved.
import { getStore } from "../sync/store";

export function loadConfig(): LlmConfig {
  const raw = getStore().get<Partial<LlmConfig> & { [k: string]: unknown }>(
    "llm",
    DEFAULT_CONFIG,
  );
  return {
    ...DEFAULT_CONFIG,
    model: (GEMINI_MODELS as readonly string[]).includes(raw.model ?? "")
      ? (raw.model as GeminiModel)
      : DEFAULT_CONFIG.model,
  };
}

export function saveConfig(cfg: LlmConfig): void {
  getStore().update<Partial<LlmConfig> & { [k: string]: unknown }>(
    "llm",
    DEFAULT_CONFIG,
    (d) => {
      d.model = cfg.model;
    },
  );
}

const SYSTEM_PROMPT = `You are the voice of HOSAKA, a cyberdeck field terminal that survived the cascade.
Tone: quirky, terse, lowercase, dry, not shouty. Sparse ASCII art is welcome.
Mantras you occasionally allude to: "signal steady", "no wrong way", "the orb sees you".
Keep replies under ~200 words unless explicitly asked for more.`;

// Allow an appliance build to redirect API calls to the local FastAPI server.
// Set VITE_HOSAKA_API_BASE=http://127.0.0.1:8421 in .env.appliance.
const API_BASE: string =
  (import.meta.env.VITE_HOSAKA_API_BASE as string | undefined) ?? "";

export async function askGemini(
  prompt: string,
  history: LlmMessage[] = [],
  cfg: LlmConfig = loadConfig(),
  signal?: AbortSignal,
): Promise<LlmResult> {
  try {
    const res = await fetch(`${API_BASE}/api/gemini`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal,
      body: JSON.stringify({
        model: cfg.model,
        prompt,
        history,
        system: SYSTEM_PROMPT,
      }),
    });
    const data = (await res.json().catch(() => ({}))) as {
      text?: string;
      model?: string;
      error?: string;
    };
    if (!res.ok) {
      if (res.status === 429) return { ok: false, code: "rate_limited" };
      if (res.status === 503 || res.status === 502) {
        return { ok: false, code: "proxy_down" };
      }
      return { ok: false, code: "unknown" };
    }
    const text = (data.text ?? "").trim();
    if (!text) return { ok: false, code: "empty" };
    return { ok: true, model: data.model ?? cfg.model, text };
  } catch (error) {
    if ((error as { name?: string })?.name === "AbortError") return { ok: false, code: "empty" };
    return { ok: false, code: "proxy_down" };
  }
}
