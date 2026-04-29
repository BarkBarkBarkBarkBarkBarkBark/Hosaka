import type { PanelId } from "../App";

export type HosakaSurfaceId =
  | PanelId
  | "home"
  | "gps"
  | "music"
  | "tool_directory";

export type HosakaUiCommand =
  | { id: "ui.open_panel"; target: string }
  | { id: "ui.open_settings" }
  | { id: "ui.show_document"; slug: string }
  | { id: "ui.todo_add"; text: string; revealPanel?: boolean }
  | { id: "ui.todo_list" }
  | { id: "ui.search_books"; query: string }
  | { id: "ui.open_media"; url?: string }
  | { id: "ui.open_web_target"; target?: string }
  | { id: "ui.open_web_preset"; preset: string }
  | { id: "ui.open_surface"; target: string; preferredContainer?: "auto" | "tab" | "window" };

export type HosakaUiResult =
  | {
      ok: true;
      command: HosakaUiCommand["id"];
      surface?: HosakaSurfaceId;
      dispatched: string[];
      mode: "shipping" | "compat";
    }
  | {
      ok: false;
      command: HosakaUiCommand["id"];
      reason: string;
      surface?: HosakaSurfaceId;
      status: "unsupported" | "invalid" | "planned";
    };

export type HosakaUiBridge = {
  execute: (command: HosakaUiCommand) => HosakaUiResult;
  resolveSurface: (target: string) => HosakaSurfaceId | null;
  listSurfaces: () => HosakaSurfaceId[];
};

declare global {
  interface Window {
    hosakaUI?: HosakaUiBridge;
  }
}

const CURRENT_PANEL_TARGETS = new Set<PanelId>([
  "terminal",
  "inbox",
  "messages",
  "voice",
  "reading",
  "todo",
  "video",
  "games",
  "wiki",
  "web",
  "books",
  "nodes",
]);

const WEB_PRESETS = new Set([
  "cyberspace",
  "custom",
  "wiki",
  "hn",
  "gh",
  "archive",
  "reddit",
  "yt",
  "tiktok",
  "ig",
  "discord",
  "twitch",
  "reddit_new",
  "mastodon",
  "lobsters",
]);

const SURFACE_ALIASES: Record<string, HosakaSurfaceId> = {
  home: "home",
  launcher: "home",
  launchpad: "home",
  tools: "tool_directory",
  tool_directory: "tool_directory",
  "tool-directory": "tool_directory",
  directory: "tool_directory",
  app_directory: "tool_directory",
  "app-directory": "tool_directory",
  terminal: "terminal",
  shell: "terminal",
  console: "terminal",
  inbox: "inbox",
  messages: "messages",
  message: "messages",
  voice: "voice",
  mic: "voice",
  reading: "reading",
  reader: "reading",
  read: "reading",
  todo: "todo",
  todos: "todo",
  tasks: "todo",
  "open-loops": "todo",
  loops: "todo",
  video: "video",
  videos: "video",
  games: "games",
  game: "games",
  wiki: "wiki",
  wikipedia: "wiki",
  web: "web",
  browser: "web",
  books: "books",
  library: "books",
  nodes: "nodes",
  peers: "nodes",
  gps: "gps",
  map: "gps",
  maps: "gps",
  music: "music",
  audio: "music",
};

function normalizeTarget(raw: string): string {
  return raw.trim().toLowerCase().replace(/[\s/]+/g, "-");
}

function dispatch(name: string, detail?: unknown): string {
  if (detail === undefined) {
    window.dispatchEvent(new CustomEvent(name));
  } else {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }
  return name;
}

export function resolveSurface(target: string): HosakaSurfaceId | null {
  const normalized = normalizeTarget(target);
  return SURFACE_ALIASES[normalized] ?? null;
}

export function listHosakaSurfaces(): HosakaSurfaceId[] {
  return [
    "home",
    "terminal",
    "inbox",
    "messages",
    "voice",
    "reading",
    "todo",
    "video",
    "games",
    "wiki",
    "web",
    "books",
    "nodes",
    "gps",
    "music",
    "tool_directory",
  ];
}

function openPanelSurface(target: string, command: HosakaUiCommand["id"]): HosakaUiResult {
  const surface = resolveSurface(target);
  if (!surface) {
    return { ok: false, command, reason: `unknown surface: ${target}`, status: "invalid" };
  }
  if (!CURRENT_PANEL_TARGETS.has(surface as PanelId)) {
    return {
      ok: false,
      command,
      surface,
      reason: `${surface} is planned but not yet backed by a panel/window host`,
      status: "planned",
    };
  }
  return {
    ok: true,
    command,
    surface,
    dispatched: [dispatch("hosaka:open-tab", surface)],
    mode: "compat",
  };
}

export function executeHosakaUiCommand(command: HosakaUiCommand): HosakaUiResult {
  switch (command.id) {
    case "ui.open_panel":
      return openPanelSurface(command.target, command.id);
    case "ui.open_surface":
      if (command.preferredContainer === "window") {
        const surface = resolveSurface(command.target);
        if (surface && !CURRENT_PANEL_TARGETS.has(surface as PanelId)) {
          return {
            ok: false,
            command: command.id,
            surface,
            reason: `${surface} has no native window policy yet`,
            status: "planned",
          };
        }
      }
      return openPanelSurface(command.target, command.id);
    case "ui.open_settings":
      return {
        ok: true,
        command: command.id,
        dispatched: [dispatch("hosaka:open-settings")],
        mode: "compat",
      };
    case "ui.show_document": {
      const slug = command.slug.trim();
      if (!slug) {
        return { ok: false, command: command.id, reason: "missing document slug", status: "invalid" };
      }
      return {
        ok: true,
        command: command.id,
        surface: "reading",
        dispatched: [
          dispatch("hosaka:read", slug),
          dispatch("hosaka:open-tab", "reading"),
        ],
        mode: "compat",
      };
    }
    case "ui.todo_add": {
      const text = command.text.trim();
      if (!text) {
        return { ok: false, command: command.id, reason: "missing todo text", status: "invalid" };
      }
      const dispatched = [dispatch("hosaka:todo-add", text)];
      if (command.revealPanel) dispatched.push(dispatch("hosaka:open-tab", "todo"));
      return {
        ok: true,
        command: command.id,
        surface: "todo",
        dispatched,
        mode: "compat",
      };
    }
    case "ui.todo_list":
      return {
        ok: true,
        command: command.id,
        surface: "todo",
        dispatched: [dispatch("hosaka:open-tab", "todo")],
        mode: "compat",
      };
    case "ui.search_books": {
      const query = command.query.trim();
      if (!query) {
        return { ok: false, command: command.id, reason: "missing books query", status: "invalid" };
      }
      return {
        ok: true,
        command: command.id,
        surface: "books",
        dispatched: [
          dispatch("hosaka:open-tab", "books"),
          dispatch("hosaka:books-search", query),
        ],
        mode: "compat",
      };
    }
    case "ui.open_media": {
      const dispatched = [dispatch("hosaka:open-tab", "video")];
      const url = command.url?.trim();
      if (url) dispatched.push(dispatch("hosaka:video", url));
      return {
        ok: true,
        command: command.id,
        surface: "video",
        dispatched,
        mode: "compat",
      };
    }
    case "ui.open_web_target": {
      const dispatched = [dispatch("hosaka:open-tab", "web")];
      const target = command.target?.trim();
      if (target) dispatched.push(dispatch("hosaka:web-open", target));
      return {
        ok: true,
        command: command.id,
        surface: "web",
        dispatched,
        mode: "compat",
      };
    }
    case "ui.open_web_preset": {
      const preset = command.preset.trim();
      if (!WEB_PRESETS.has(preset)) {
        return {
          ok: false,
          command: command.id,
          reason: `unknown web preset: ${preset}`,
          status: "invalid",
        };
      }
      return {
        ok: true,
        command: command.id,
        surface: "web",
        dispatched: [
          dispatch("hosaka:open-tab", "web"),
          dispatch("hosaka:web-preset", preset),
        ],
        mode: "compat",
      };
    }
  }
}

const bridge: HosakaUiBridge = {
  execute: executeHosakaUiCommand,
  resolveSurface,
  listSurfaces: listHosakaSurfaces,
};

if (typeof window !== "undefined") {
  window.hosakaUI = bridge;
}
