// LLM provider configuration helpers for the frontend.
//
// Non-sensitive fields (provider, model, base_url) flow through the shared
// sync Store — on the appliance they propagate to peer nodes over the
// tailnet, on hosted builds they stay in the LocalStore's localStorage.
// The API key itself is NEVER stored client-side in any form; it travels
// only over the wire to PATCH /api/llm-key and lives in the server-side
// OS keychain from there.

import { getStore } from "../sync/store";

export type LlmProvider = "openai" | "openai-compatible";

export const PROVIDERS: { id: LlmProvider; label: string; defaultModel: string }[] = [
  { id: "openai",            label: "OpenAI",                         defaultModel: "gpt-4o-mini" },
  { id: "openai-compatible", label: "OpenAI-compatible (Ollama, etc)", defaultModel: "llama3"      },
];

export type ProviderConfig = {
  provider: LlmProvider;
  model:    string;
  base_url: string; // only relevant for openai-compatible
};

export type LlmStatus = ProviderConfig & { configured: boolean };

// Shape of the synced "llm" doc. We co-locate both the provider config and
// the gemini model preference here; both are non-sensitive strings.
type LlmDoc = Partial<ProviderConfig> & {
  model?: string;    // also used by the gemini client for its own model field
  provider?: LlmProvider;
  base_url?: string;
};
const LLM_DOC_DEFAULTS: LlmDoc = {};

export const DEFAULT_PROVIDER_CONFIG: ProviderConfig = {
  provider: "openai",
  model:    "gpt-4o-mini",
  base_url: "",
};

export function loadProviderConfig(): ProviderConfig {
  const raw = getStore().get<LlmDoc>("llm", LLM_DOC_DEFAULTS);
  return {
    provider: raw.provider ?? DEFAULT_PROVIDER_CONFIG.provider,
    model:    raw.model    ?? DEFAULT_PROVIDER_CONFIG.model,
    base_url: raw.base_url ?? DEFAULT_PROVIDER_CONFIG.base_url,
  };
}

export function saveProviderConfig(cfg: ProviderConfig): void {
  getStore().update<LlmDoc>("llm", LLM_DOC_DEFAULTS, (d) => {
    d.provider = cfg.provider;
    d.model    = cfg.model;
    d.base_url = cfg.base_url;
  });
}

/** Fetch current server-side LLM status (never returns the key). */
export async function fetchLlmStatus(): Promise<LlmStatus> {
  try {
    const r = await fetch("/api/llm-key");
    const d = await r.json() as Partial<LlmStatus>;
    return {
      provider:   (d.provider as LlmProvider) ?? "openai",
      model:      d.model    ?? "",
      base_url:   d.base_url ?? "",
      configured: d.configured ?? false,
    };
  } catch {
    return { ...DEFAULT_PROVIDER_CONFIG, configured: false };
  }
}

/** Save provider config + API key to the server.  Returns true on success. */
export async function saveLlmToServer(
  cfg: ProviderConfig,
  api_key: string,
): Promise<boolean> {
  try {
    const body: Record<string, string> = {
      provider: cfg.provider,
      model:    cfg.model,
      base_url: cfg.base_url,
      api_key,
    };
    const r = await fetch("/api/llm-key", {
      method:  "PATCH",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const d = await r.json() as { ok?: boolean };
    if (d.ok) saveProviderConfig(cfg); // mirror non-sensitive fields locally
    return d.ok === true;
  } catch {
    return false;
  }
}
