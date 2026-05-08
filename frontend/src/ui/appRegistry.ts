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
  | "vscode"
  | "firefox"
  | "telegram"
  | "betterbird"
  | "alienarena"
  | "slack"
  | "steam"
  | "obsidian"
  | "apostrophe"
  | "wike"
  | "webarchives"
  | "keepassxc"
  | "readetexts"
  | "tonearm"
  | "isoimagewriter"
  | "gqrx"
  | "receiver"
  | "ottomatic"
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
export type HostScope = "any" | "electron-only" | "web" | "linux";
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
  /**
   * Flatpak architectures Flathub actually publishes for this app.
   * Used to gate the install button on hosts whose arch is not in the
   * list (e.g. spotify/steam are x86_64-only and will never install on
   * a Pi 3B+ which is aarch64). Empty/undefined = no constraint.
   */
  flatpakArches?: Array<"x86_64" | "aarch64" | "i386" | "arm">;
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
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    flatpakArches: ["x86_64"],
    maintainerNote: "Flatpak: com.spotify.Client — x86_64-only on Flathub; install fails gracefully on aarch64.",
    agentNote: "Prefer external-app launch via /api/v1/apps/spotify; surface install state in the panel.",
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
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web", "system-browser"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    flatpakArches: ["x86_64"],
    maintainerNote: "Flatpak: com.discordapp.Discord (x86_64-only on Flathub).",
    agentNote: "Launch via /api/v1/apps/discord; show install state if missing.",
  },
  {
    id: "foliate",
    title: "foliate",
    description: "epub / mobi reader for the local library.",
    glyph: "❧",
    aliases: ["foliate", "epub", "reader"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: com.github.johnfactotum.Foliate (aarch64 + x86_64).",
  },
  {
    id: "vscode",
    title: "vs code",
    description: "visual studio code, edit source on the device itself.",
    glyph: "⌗",
    aliases: ["vscode", "code", "editor"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: com.visualstudio.code (aarch64 + x86_64).",
  },
  {
    id: "firefox",
    title: "firefox",
    description: "real persistent browser session, separate from the embedded web panel.",
    glyph: "🦊",
    aliases: ["firefox", "mozilla"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.mozilla.firefox (aarch64 + x86_64).",
  },
  {
    id: "telegram",
    title: "telegram",
    description: "telegram desktop, personal chat. signs in inside the launched window.",
    glyph: "✈",
    aliases: ["telegram", "tg"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.telegram.desktop (aarch64 + x86_64).",
  },
  {
    id: "betterbird",
    title: "betterbird",
    description: "thunderbird-derived mail client. local imap/smtp.",
    glyph: "✉",
    aliases: ["betterbird", "mail", "thunderbird"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: eu.betterbird.Betterbird (aarch64 + x86_64).",
  },
  {
    id: "alienarena",
    title: "alien arena",
    description: "retro arena fps. easter-egg game bundled with hosaka.",
    glyph: "⚔",
    aliases: ["alienarena", "alien-arena", "aa"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.alienarena.alienarena (aarch64 + x86_64).",
  },
  {
    id: "slack",
    title: "slack",
    description: "slack desktop client. x86_64-only on flathub today.",
    glyph: "#",
    aliases: ["slack"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    flatpakArches: ["x86_64"],
    maintainerNote: "Flatpak: com.slack.Slack — install will fail on aarch64 (Pi); panel surfaces the error.",
  },
  {
    id: "steam",
    title: "steam",
    description: "valve steam. x86_64-only on flathub today.",
    glyph: "♟",
    aliases: ["steam"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    flatpakArches: ["x86_64"],
    maintainerNote: "Flatpak: com.valvesoftware.Steam — install will fail on aarch64 (Pi); panel surfaces the error.",
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
    id: "obsidian",
    title: "obsidian",
    description: "markdown vault, knowledge graph, daily notes. central writing surface for the operator.",
    glyph: "◇",
    aliases: ["obsidian", "vault", "notes"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    flatpakArches: ["x86_64", "aarch64"],
    maintainerNote: "Flatpak: md.obsidian.Obsidian (aarch64 + x86_64). Opens the canonical ~/Vault markdown directory.",
    agentNote: "Treat ~/Vault as a future agent-readable vault; today, write through /api/v1/docs/* on the docs panel.",
  },
  {
    id: "apostrophe",
    title: "apostrophe",
    description: "distraction-free markdown editor; the aarch64-friendly answer to obsidian.",
    glyph: "✒",
    aliases: ["apostrophe", "markdown", "writer"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.gnome.gitlab.somas.Apostrophe (aarch64 + x86_64).",
  },
  {
    id: "wike",
    title: "wike",
    description: "wikipedia reader with offline article archive. fast curiosity loop.",
    glyph: "ⓦ",
    aliases: ["wike", "wikipedia-reader"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: com.github.hugolabe.Wike (aarch64 + x86_64). Pairs with webarchives.",
  },
  {
    id: "webarchives",
    title: "web archives",
    description: "offline wikipedia / wiktionary / gutenberg via .zim files. doomsday-prep tier.",
    glyph: "⛁",
    aliases: ["webarchives", "web-archives", "kiwix", "zim"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: com.github.birros.WebArchives. Drop .zim files into ~/WebArchives.",
    agentNote: "Suggest seeding from kiwix.org — wikipedia/stackoverflow/gutenberg dumps work offline.",
  },
  {
    id: "keepassxc",
    title: "keepassxc",
    description: "local-first encrypted password vault. no cloud, no account.",
    glyph: "⚷",
    aliases: ["keepass", "keepassxc", "passwords"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.keepassxc.KeePassXC (aarch64 + x86_64). Hosaka never reads the vault.",
  },
  {
    id: "readetexts",
    title: "read etexts",
    description: "sugar-labs reader for plain-text and minimal-html books with text-to-speech.",
    glyph: "✐",
    aliases: ["readetexts", "read-etexts", "sugar-read"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.sugarlabs.ReadETexts (aarch64 + x86_64). Pairs with foliate.",
  },
  {
    id: "tonearm",
    title: "tonearm",
    description: "local music library player; album-art-first browsing of ~/Music.",
    glyph: "♪",
    aliases: ["tonearm", "music-player"],
    family: "integration",
    backgroundCapable: true,
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: dev.dergs.Tonearm (aarch64 + x86_64). Library at ~/Music; seeded by scripts/seed-music.sh.",
  },
  {
    id: "isoimagewriter",
    title: "iso writer",
    description: "flash bootable usb drives from .iso files. recovery-image friendly.",
    glyph: "☸",
    aliases: ["isoimagewriter", "iso-writer", "flash-iso", "usb-writer"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: org.kde.isoimagewriter (aarch64 + x86_64). Needs portal-granted device access at run time.",
  },
  {
    id: "gqrx",
    title: "gqrx",
    description: "sdr scanner for rtl-sdr dongles. AM/FM/shortwave/ham/ADS-B sweeps.",
    glyph: "≋",
    aliases: ["gqrx", "sdr", "rtl-sdr", "scanner", "radio-scanner"],
    family: "integration",
    backgroundCapable: true,
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: dk.gqrx.gqrx (aarch64 + x86_64). Plug the RTL-SDR dongle before launch.",
    agentNote: "Suggest plugging the RTL-SDR dongle in before launch; gqrx auto-detects on start.",
  },
  {
    id: "receiver",
    title: "receiver",
    description: "internet-radio tuner backed by the radio-browser database. no antenna needed.",
    glyph: "·))",
    aliases: ["receiver", "internet-radio", "radio-browser"],
    family: "integration",
    backgroundCapable: true,
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: io.github.meehow.Receiver (aarch64 + x86_64). Pairs with gqrx for the over-the-air vs. internet split.",
  },
  {
    id: "ottomatic",
    title: "otto matic",
    description: "the open-source 2001 pangea 3d action game. arcade downtime.",
    glyph: "♠",
    aliases: ["ottomatic", "otto-matic", "otto"],
    family: "integration",
    showInLauncher: true,
    status: "shipping",
    preferredHost: "external-app",
    fallbackHosts: ["web"],
    installStrategy: "catalog",
    hostScope: "linux",
    embedPolicy: "no_embed",
    maintainerNote: "Flatpak: io.jor.ottomatic (aarch64 + x86_64). Pi 3B+ runs it under software GL.",
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

export function isHostScopeAllowed(scope: HostScope | undefined, platform: string | null): boolean {
  if (!scope || scope === "any") return true;
  if (scope === "web") return true; // web-only is shown everywhere; runtime gates the launch path
  if (scope === "electron-only") return true; // host check happens at launch time
  if (scope === "linux") {
    // null platform = unknown (e.g. before /apps/capabilities resolves) — allow,
    // so the apps appear on the Pi during boot. Once resolved, hide on non-linux.
    if (!platform) return true;
    return /linux/i.test(platform);
  }
  return true;
}

export function isAppEnabled(app: AppDefinition, flags: AppFlags, platform: string | null = null): boolean {
  if (!isHostScopeAllowed(app.hostScope, platform)) return false;
  if (!app.requires) return app.status !== "planned";
  return flags[app.requires] && app.status !== "planned";
}

export function listEnabledApps(flags: AppFlags, platform: string | null = null): AppDefinition[] {
  return APP_REGISTRY.filter((app) => isAppEnabled(app, flags, platform));
}

export function resolveAppId(target: string): AppId | null {
  const normalized = target.trim().toLowerCase().replace(/[\s/]+/g, "-");
  if (!normalized) return null;
  const hit = APP_REGISTRY.find((app) => [app.id, ...app.aliases].includes(normalized));
  return hit?.id ?? null;
}
