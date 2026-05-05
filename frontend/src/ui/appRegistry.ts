export type PanelId =
  | "terminal"
  | "inbox"
  | "messages"
  | "reading"
  | "todo"
  | "video"
  | "games"
  | "wiki"
  | "web"
  | "books"
  | "docs"
  | "diagnostics"
  | "voice"
  | "nodes";

export type AppId =
  | PanelId
  | "home"
  | "tool_directory"
  | "workbench"
  | "music"
  | "gps"
  | "app_store"
  | "spotify"
  | "kindle"
  | "kcc"
  | "discord"
  | "foliate"
  | "simulcast"
  | "device_mic"
  | "device_cam"
  | "device_spk"
  | "help";

export type AppFlags = {
  inboxEnabled: boolean;
  webPanelEnabled: boolean;
  nodesEnabled: boolean;
};

export type PreferredHost = "electron" | "web" | "external-app" | "system-browser";
export type InstallStrategy = "builtin" | "catalog" | "linux_package" | "windows_package" | "manual";
export type HostScope = "any" | "electron-only" | "web";
export type EmbedPolicy = "prefer_embed" | "allow_escape" | "no_embed";
export type AppFamily = "core" | "integration";

export type AppDefinition = {
  id: AppId;
  title: string;
  description: string;
  glyph: string;
  aliases: string[];
  family?: AppFamily;
  requires?: keyof AppFlags;
  backgroundCapable?: boolean;
  defaultBackground?: boolean;
  closable?: boolean;
  showInLauncher?: boolean;
  status?: "shipping" | "planned";
  preferredHost?: PreferredHost;
  fallbackHosts?: PreferredHost[];
  installStrategy?: InstallStrategy;
  hostScope?: HostScope;
  embedPolicy?: EmbedPolicy;
  maintainerNote?: string;
  agentNote?: string;
};

export const HOST_LABELS: Record<PreferredHost, string> = {
  electron: "Electron",
  web: "Web",
  "external-app": "External App",
  "system-browser": "Browser",
};

export const INSTALL_LABELS: Record<InstallStrategy, string> = {
  builtin: "Built-in",
  catalog: "Catalog",
  linux_package: "Linux pkg",
  windows_package: "Windows pkg",
  manual: "Manual",
};

export const APP_REGISTRY: AppDefinition[] = [
  {
    id: "home",
    title: "desktop",
    description: "home surface, launcher, and recent signal.",
    glyph: "⌂",
    aliases: ["home", "desktop", "launcher", "launchpad"],
    family: "core",
    closable: false,
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
    maintainerNote: "Prefer Electron for full device integration; automatically fall back to browser when desktop runtime is unavailable.",
    agentNote: "Use Electron when present; otherwise launch the browser-safe path without assuming native desktop capabilities.",
  },
  {
    id: "workbench",
    title: "workbench",
    description: "lightweight operator studio: tree, preview, chat, command deck.",
    glyph: "▤",
    aliases: ["workbench", "studio", "editor", "files", "project"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "docs",
    title: "documents",
    description: "markdown notes, agent-authored summaries, and todo lists.",
    glyph: "✎",
    aliases: ["docs", "documents", "notes", "markdown", "memory", "journal"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
    maintainerNote: "Picoclaw agent writes here via /api/v1/docs/*; voice tools write_doc/append_doc target this surface.",
    agentNote: "Save markdown summaries, todos, and notes here so the operator can find them later.",
  },
  {
    id: "diagnostics",
    title: "devices",
    description: "peripherals, network, system health, and live media tests.",
    glyph: "⚇",
    aliases: ["devices", "diagnostics", "diag", "peripherals", "hardware", "audio", "camera", "network"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
    maintainerNote: "Uses /api/v1/diag/snapshot, the same contract consumed by /device and hosaka diag.",
    agentNote: "Open this app when the operator asks to test microphone, camera, network, USB, Bluetooth, battery, or disk.",
  },
  {
    id: "tool_directory",
    title: "apps",
    description: "directory of launchable surfaces and planned modules.",
    glyph: "☰",
    aliases: ["apps", "tools", "directory", "tool-directory", "app-directory"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
    maintainerNote: "The registry is the source of truth for host preference and install policy.",
    agentNote: "Use registry metadata to choose launch targets and allowed containers.",
  },
  {
    id: "terminal",
    title: "terminal",
    description: "console shell, agent channel, and staged commands.",
    glyph: "›_",
    aliases: ["terminal", "shell", "console"],
    family: "core",
    closable: false,
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "inbox",
    title: "inbox",
    description: "messages arriving from the outside signal.",
    glyph: "☷",
    aliases: ["inbox"],
    family: "core",
    requires: "inboxEnabled",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "messages",
    title: "messages",
    description: "outbound notes, webhook bridge, and session relays.",
    glyph: "✉",
    aliases: ["messages", "message"],
    family: "core",
    showInLauncher: false,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "voice",
    title: "voice",
    description: "voice orb, realtime lane, and agent speech turns.",
    glyph: "◎",
    aliases: ["voice", "mic", "microphone"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "reading",
    title: "reading",
    description: "documents, collections, and long-form signal.",
    glyph: "❑",
    aliases: ["reading", "reader", "read"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "todo",
    title: "open loops",
    description: "tasks, reminders, and loose edges.",
    glyph: "▣",
    aliases: ["todo", "todos", "tasks", "loops", "open-loops"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "video",
    title: "video",
    description: "media playback and streaming surfaces.",
    glyph: "▶",
    aliases: ["video", "videos", "media"],
    family: "core",
    backgroundCapable: true,
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "allow_escape",
  },
  {
    id: "games",
    title: "games",
    description: "arcade surfaces and playful downtime.",
    glyph: "◆",
    aliases: ["games", "game"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "wiki",
    title: "wiki",
    description: "wikipedia roulette and fast curiosity jumps.",
    glyph: "W",
    aliases: ["wiki", "wikipedia"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "allow_escape",
  },
  {
    id: "web",
    title: "internet",
    description: "browser surface for urls, presets, and hosaka:// pages.",
    glyph: "⌁",
    aliases: ["web", "browser", "internet"],
    family: "core",
    requires: "webPanelEnabled",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "allow_escape",
  },
  {
    id: "books",
    title: "books",
    description: "book search and library storefront view.",
    glyph: "📖",
    aliases: ["books", "library"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "allow_escape",
  },
  {
    id: "nodes",
    title: "nodes",
    description: "mesh status, peers, and sync topology.",
    glyph: "◈",
    aliases: ["nodes", "peers"],
    family: "core",
    requires: "nodesEnabled",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "music",
    title: "hosaka radio",
    description: "am/fm/wideband, wikicommons public-domain audio, and local music library playback.",
    glyph: "♫",
    aliases: ["music", "audio", "radio", "hosaka-radio", "wikicommons", "am", "fm", "wideband", "listen"],
    family: "integration",
    backgroundCapable: true,
    defaultBackground: true,
    showInLauncher: true,
    status: "shipping",
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "allow_escape",
    maintainerNote: "Prefer Electron for device audio and radio integrations; browser fallback can cover local/public-domain playback only.",
    agentNote: "Use Electron when present; otherwise launch the browser-safe path without assuming native desktop capabilities.",
  },
  {
    id: "gps",
    title: "maps",
    description: "mapping and location surfaces.",
    glyph: "⌖",
    aliases: ["gps", "maps", "map"],
    family: "integration",
    showInLauncher: false,
    status: "planned",
    preferredHost: "electron",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "allow_escape",
  },
  {
    id: "app_store",
    title: "app store",
    description: "flathub catalog browser; stage manifests and install flatpak apps from the kiosk.",
    glyph: "⬚",
    aliases: ["app-store", "store", "catalog", "flathub"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "any",
    embedPolicy: "allow_escape",
    maintainerNote: "Electron-Store/electron-app-store looks more useful as a reference than a current dependency, since its releases appear old and effectively stale.",
    agentNote: "Never assume external apps exist; check capability and fail safely.",
  },
  {
    id: "spotify",
    title: "spotify",
    description: "desktop playback handoff for spotify alongside hosaka radio and local/public-domain audio.",
    glyph: "♬",
    aliases: ["spotify"],
    family: "integration",
    backgroundCapable: true,
    defaultBackground: true,
    showInLauncher: false,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "catalog",
    hostScope: "any",
    embedPolicy: "no_embed",
    maintainerNote: "Prefer Electron desktop apps, allow Linux/Windows package installs when necessary, and disable features on web when unsupported.",
    agentNote: "Prefer Electron launches when available; fall back only if metadata permits.",
  },
  {
    id: "kindle",
    title: "kindle",
    description: "desktop kindle reader integration, with linux package guidance and browser fallback where needed.",
    glyph: "🕮",
    aliases: ["kindle"],
    family: "integration",
    showInLauncher: false,
    status: "planned",
    preferredHost: "external-app",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "linux_package",
    hostScope: "any",
    embedPolicy: "no_embed",
    maintainerNote: "External apps should be launched via capability-checked handoff, not assumed embedded.",
    agentNote: "Never assume external apps exist; check capability and fail safely.",
  },
  {
    id: "discord",
    title: "discord",
    description: "community chat, voice rooms, and call handoff beyond the existing web preset.",
    glyph: "☵",
    aliases: ["discord"],
    family: "integration",
    showInLauncher: false,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "linux_package",
    hostScope: "any",
    embedPolicy: "no_embed",
    maintainerNote: "Treat Instagram, TikTok, and Discord as planned external app integrations, not presumed embedded iframe experiences.",
    agentNote: "Never assume external apps exist; check capability and fail safely.",
  },
  {
    id: "simulcast",
    title: "simulcast",
    description: "broadcast one session across platforms with synchronized publishing and control.",
    glyph: "⟠",
    aliases: ["simulcast", "stream", "multistream"],
    family: "integration",
    backgroundCapable: true,
    showInLauncher: false,
    status: "planned",
    preferredHost: "electron",
    fallbackHosts: ["external-app", "web"],
    installStrategy: "manual",
    hostScope: "any",
    embedPolicy: "no_embed",
    maintainerNote: "Simulcast requires actual capture and output plumbing; simply listing web apps does not implement it.",
    agentNote: "Use registry metadata to choose launch targets and allowed containers.",
  },
  {
    id: "device_mic",
    title: "mic check",
    description: "live microphone preview, levels, and device picker.",
    glyph: "🎙",
    aliases: ["device-mic", "mic-check", "check-mic"],
    family: "core",
    showInLauncher: false,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
    agentNote: "Open this when the user wants to test or pick a microphone.",
  },
  {
    id: "device_cam",
    title: "cam check",
    description: "live camera preview and device picker.",
    glyph: "📷",
    aliases: ["device-cam", "cam-check", "check-cam"],
    family: "core",
    showInLauncher: false,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "device_spk",
    title: "spk check",
    description: "speaker tone test and output device picker.",
    glyph: "🔊",
    aliases: ["device-spk", "spk-check", "check-spk"],
    family: "core",
    showInLauncher: false,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
  {
    id: "help",
    title: "help",
    description: "keyboard shortcuts and slash command reference.",
    glyph: "?",
    aliases: ["help", "shortcuts", "keys", "cheatsheet"],
    family: "core",
    showInLauncher: true,
    preferredHost: "electron",
    fallbackHosts: ["web"],
    installStrategy: "builtin",
    hostScope: "any",
    embedPolicy: "prefer_embed",
  },
];

const APP_MAP = new Map(APP_REGISTRY.map((app) => [app.id, app]));

export function getAppDefinition(appId: AppId): AppDefinition | undefined {
  return APP_MAP.get(appId);
}

export function isAppEnabled(app: AppDefinition, flags: AppFlags): boolean {
  if (!app.requires) return app.status !== "planned";
  return flags[app.requires] && app.status !== "planned";
}

export function listEnabledApps(flags: AppFlags): AppDefinition[] {
  return APP_REGISTRY.filter((app) => isAppEnabled(app, flags));
}

export function resolveAppId(target: string): AppId | null {
  const normalized = target.trim().toLowerCase().replace(/[\s/]+/g, "-");
  if (!normalized) return null;
  const hit = APP_REGISTRY.find((app) => [app.id, ...app.aliases].includes(normalized));
  return hit?.id ?? null;
}
