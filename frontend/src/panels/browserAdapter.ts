export type BrowserMode =
  | "web-fallback"
  | "external-browser"
  | "native-webview"
  | "remote-browser";

export type InternalPage =
  | "home"
  | "terminal"
  | "reading"
  | "todo"
  | "video"
  | "games"
  | "wiki"
  | "web"
  | "books"
  | "messages";

export type BrowserOpenResult =
  | { kind: "internal"; url: string; page: InternalPage }
  | { kind: "native-webview"; url: string; mode: BrowserMode }
  | { kind: "external-browser"; url: string; mode: BrowserMode; launched: boolean }
  | { kind: "blocked"; url: string; mode: BrowserMode; reason: string }
  | { kind: "unsupported"; input: string; reason: string };

type NativeBridge = {
  mode?: BrowserMode;
  launchExternal?: (url: string) => boolean | Promise<boolean>;
  launchNativeWebview?: (url: string) => boolean | Promise<boolean>;
  openRemoteSession?: (url: string) => boolean | Promise<boolean>;
};

declare global {
  interface Window {
    hosakaBrowserAdapter?: NativeBridge;
  }
}

const INTERNAL_PAGES = new Set<InternalPage>([
  "home",
  "terminal",
  "reading",
  "todo",
  "video",
  "games",
  "wiki",
  "web",
  "books",
  "messages",
]);

function normalizeExternalUrl(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  if (/^https?:\/\//i.test(value)) {
    try {
      const parsed = new URL(value);
      if (!["http:", "https:"].includes(parsed.protocol)) return null;
      return parsed.href;
    } catch {
      return null;
    }
  }
  try {
    return new URL(`https://${value}`).href;
  } catch {
    return null;
  }
}

export function parseInternalPage(input: string): InternalPage | null {
  const trimmed = input.trim();
  if (!trimmed) return "home";
  if (trimmed === "/" || trimmed === "home") return "home";
  if (/^hosaka:\/\/home\/?$/i.test(trimmed)) return "home";

  const panelMatch = trimmed.match(/^\/?(terminal|messages|reading|todo|video|games|wiki|web|books)$/i);
  if (panelMatch) {
    const id = panelMatch[1].toLowerCase() as InternalPage;
    return INTERNAL_PAGES.has(id) ? id : null;
  }

  const hosakaPanelMatch = trimmed.match(/^hosaka:\/\/panel\/(terminal|messages|reading|todo|video|games|wiki|web|books)\/?$/i);
  if (hosakaPanelMatch) {
    const id = hosakaPanelMatch[1].toLowerCase() as InternalPage;
    return INTERNAL_PAGES.has(id) ? id : null;
  }

  return null;
}

export function canEmbed(url: string): boolean {
  return parseInternalPage(url) !== null;
}

export function getBrowserMode(): BrowserMode {
  const bridge = window.hosakaBrowserAdapter;
  if (bridge?.mode) return bridge.mode;
  if (bridge?.launchNativeWebview) return "native-webview";
  if (bridge?.openRemoteSession) return "remote-browser";
  if (bridge?.launchExternal) return "external-browser";
  return "web-fallback";
}

export async function launchExternal(url: string): Promise<boolean> {
  const bridge = window.hosakaBrowserAdapter;
  if (bridge?.launchExternal) {
    return Boolean(await bridge.launchExternal(url));
  }
  const opened = window.open(url, "_blank", "noopener,noreferrer");
  return Boolean(opened);
}

export async function launchNativeWebview(url: string): Promise<boolean> {
  const bridge = window.hosakaBrowserAdapter;
  if (bridge?.launchNativeWebview) {
    return Boolean(await bridge.launchNativeWebview(url));
  }
  return false;
}

export async function openUrl(rawInput: string): Promise<BrowserOpenResult> {
  const internal = parseInternalPage(rawInput);
  if (internal) {
    const url = internal === "home" ? "hosaka://home" : `hosaka://panel/${internal}`;
    return { kind: "internal", url, page: internal };
  }

  const normalized = normalizeExternalUrl(rawInput);
  if (!normalized) {
    return { kind: "unsupported", input: rawInput, reason: "enter a valid http(s) URL or hosaka:// target." };
  }

  const mode = getBrowserMode();
  if (mode === "native-webview") {
    const launched = await launchNativeWebview(normalized);
    if (launched) return { kind: "native-webview", url: normalized, mode };
    return {
      kind: "blocked",
      url: normalized,
      mode,
      reason: "native webview adapter is unavailable for this build.",
    };
  }

  if (mode === "remote-browser") {
    const launched = Boolean(await window.hosakaBrowserAdapter?.openRemoteSession?.(normalized));
    if (launched) return { kind: "external-browser", url: normalized, mode, launched: true };
    return {
      kind: "blocked",
      url: normalized,
      mode,
      reason: "remote browser session is not configured yet.",
    };
  }

  const launched = await launchExternal(normalized);
  return {
    kind: "external-browser",
    url: normalized,
    mode,
    launched,
  };
}
