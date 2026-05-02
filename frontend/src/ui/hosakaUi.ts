import {
  APP_REGISTRY,
  resolveAppId,
  type AppId,
} from "./appRegistry";

export type HosakaSurfaceId =
  | AppId;

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
  | { id: "ui.open_surface"; target: string; preferredContainer?: "auto" | "tab" | "window" }
  | { id: "ui.stage_terminal_command"; command: string; autoSubmit?: boolean };

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
  return resolveAppId(normalizeTarget(target));
}

export function listHosakaSurfaces(): HosakaSurfaceId[] {
  return APP_REGISTRY.map((app) => app.id);
}

function openPanelSurface(target: string, command: HosakaUiCommand["id"]): HosakaUiResult {
  const surface = resolveSurface(target);
  if (!surface) {
    return { ok: false, command, reason: `unknown surface: ${target}`, status: "invalid" };
  }
  return {
    ok: true,
    command,
    surface,
    dispatched: [dispatch("hosaka:open-app", { appId: surface })],
    mode: "shipping",
  };
}

export function executeHosakaUiCommand(command: HosakaUiCommand): HosakaUiResult {
  switch (command.id) {
    case "ui.open_panel":
      return openPanelSurface(command.target, command.id);
    case "ui.open_surface":
      return openPanelSurface(command.target, command.id);
    case "ui.stage_terminal_command": {
      const text = command.command.trim();
      if (!text) {
        return { ok: false, command: command.id, reason: "missing command text", status: "invalid" };
      }
      return {
        ok: true,
        command: command.id,
        surface: "terminal",
        dispatched: [
          dispatch("hosaka:open-app", { appId: "terminal" }),
          dispatch("hosaka:terminal-stage-command", { command: text, autoSubmit: Boolean(command.autoSubmit) }),
        ],
        mode: "shipping",
      };
    }
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
          dispatch("hosaka:open-app", { appId: "reading" }),
        ],
        mode: "shipping",
      };
    }
    case "ui.todo_add": {
      const text = command.text.trim();
      if (!text) {
        return { ok: false, command: command.id, reason: "missing todo text", status: "invalid" };
      }
      const dispatched = [dispatch("hosaka:todo-add", text)];
      if (command.revealPanel) dispatched.push(dispatch("hosaka:open-app", { appId: "todo" }));
      return {
        ok: true,
        command: command.id,
        surface: "todo",
        dispatched,
        mode: "shipping",
      };
    }
    case "ui.todo_list":
      return {
        ok: true,
        command: command.id,
        surface: "todo",
        dispatched: [dispatch("hosaka:open-app", { appId: "todo" })],
        mode: "shipping",
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
          dispatch("hosaka:open-app", { appId: "books" }),
          dispatch("hosaka:books-search", query),
        ],
        mode: "shipping",
      };
    }
    case "ui.open_media": {
      const dispatched = [dispatch("hosaka:open-app", { appId: "video" })];
      const url = command.url?.trim();
      if (url) dispatched.push(dispatch("hosaka:video", url));
      return {
        ok: true,
        command: command.id,
        surface: "video",
        dispatched,
        mode: "shipping",
      };
    }
    case "ui.open_web_target": {
      const dispatched = [dispatch("hosaka:open-app", { appId: "web" })];
      const target = command.target?.trim();
      if (target) dispatched.push(dispatch("hosaka:web-open", target));
      return {
        ok: true,
        command: command.id,
        surface: "web",
        dispatched,
        mode: "shipping",
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
          dispatch("hosaka:open-app", { appId: "web" }),
          dispatch("hosaka:web-preset", preset),
        ],
        mode: "shipping",
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
