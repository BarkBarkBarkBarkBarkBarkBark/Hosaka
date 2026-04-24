// LLM provider configuration helpers for the frontend.
//
// Non-sensitive fields (provider, model, base_url) are cached in localStorage
// so the UI reflects the current state without an extra fetch on every open.
// The API key is NEVER stored in localStorage — it only travels over the
// wire to PATCH /api/llm-key and is held server-side only.

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

const STORAGE_KEY = "hosaka.llm-provider.v1";

export const DEFAULT_PROVIDER_CONFIG: ProviderConfig = {
  provider: "openai",
  model:    "gpt-4o-mini",
  base_url: "",
};

export function loadProviderConfig(): ProviderConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PROVIDER_CONFIG };
    return { ...DEFAULT_PROVIDER_CONFIG, ...(JSON.parse(raw) as Partial<ProviderConfig>) };
  } catch {
    return { ...DEFAULT_PROVIDER_CONFIG };
  }
}

export function saveProviderConfig(cfg: ProviderConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
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
