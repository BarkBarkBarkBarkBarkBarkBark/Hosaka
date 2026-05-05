import {
  APP_REGISTRY,
  resolveAppId,
  type AppId,
} from "./appRegistry";
import {
  OVERLAY_CLOSE_ALL_EVENT,
  OVERLAY_CLOSE_EVENT,
  OVERLAY_OPEN_EVENT,
  type OverlaySurfaceId,
} from "./overlayState";

export type HosakaSurfaceId =
  | AppId
  | OverlaySurfaceId;

export type DeviceCheckKind = "mic" | "cam" | "spk";

export type HosakaUiCommand =
  | { id: "ui.open_panel"; target: string }
  | { id: "ui.show_document"; slug: string }
  | { id: "ui.todo_add"; text: string; revealPanel?: boolean }
  | { id: "ui.todo_list" }
  | { id: "ui.search_books"; query: string }
  | { id: "ui.open_media"; url?: string }
  | { id: "ui.open_web_target"; target?: string }
  | { id: "ui.open_web_preset"; preset: string }
  | { id: "ui.open_surface"; target: string; preferredContainer?: "auto" | "tab" | "window" | "overlay" }
  | { id: "ui.close_surface"; target: string }
  | { id: "ui.stage_terminal_command"; command: string; autoSubmit?: boolean }
  | { id: "ui.prefill_cmdline"; text: string; submit?: boolean; focus?: boolean }
  | { id: "ui.toggle_menu" }
  | { id: "ui.toggle_orb" }
  | { id: "ui.toggle_chrome" }
  | { id: "ui.focus_terminal" }
  | { id: "ui.launch_app"; target: string }
  | { id: "ui.device_check"; kind: DeviceCheckKind }
  | { id: "ui.device_select"; kind: "mic" | "cam" | "spk"; deviceId: string }
  | { id: "ui.show_diagnostics" };

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
  snapshotDeviceAgentPayload: (kind: DeviceCheckKind) => Promise<unknown>;
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

const OVERLAY_ALIASES: Record<string, OverlaySurfaceId> = {
  mic: "mic_check",
  microphone: "mic_check",
  "mic-check": "mic_check",
  "mic_check": "mic_check",
  cam: "cam_check",
  camera: "cam_check",
  "cam-check": "cam_check",
  "cam_check": "cam_check",
  spk: "spk_check",
  speaker: "spk_check",
  "spk-check": "spk_check",
  "spk_check": "spk_check",
  diag: "diag",
  diagnostics: "diag",
};

function resolveOverlayId(target: string): OverlaySurfaceId | null {
  return OVERLAY_ALIASES[normalizeTarget(target)] ?? null;
}

const DEVICE_STORAGE: Record<"mic" | "cam" | "spk", string> = {
  mic: "hosaka.device.mic",
  cam: "hosaka.device.cam",
  spk: "hosaka.device.spk",
};

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

function openPanelSurface(
  target: string,
  command: HosakaUiCommand["id"],
  preferOverlay = false,
): HosakaUiResult {
  if (preferOverlay) {
    const overlay = resolveOverlayId(target);
    if (overlay) {
      return {
        ok: true,
        command,
        surface: overlay,
        dispatched: [dispatch(OVERLAY_OPEN_EVENT, { id: overlay })],
        mode: "shipping",
      };
    }
  }
  const surface = resolveSurface(target);
  if (!surface) {
    const overlay = resolveOverlayId(target);
    if (overlay) {
      return {
        ok: true,
        command,
        surface: overlay,
        dispatched: [dispatch(OVERLAY_OPEN_EVENT, { id: overlay })],
        mode: "shipping",
      };
    }
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
      return openPanelSurface(
        command.target,
        command.id,
        command.preferredContainer === "overlay",
      );
    case "ui.launch_app":
      return openPanelSurface(command.target, command.id);
    case "ui.close_surface": {
      const overlay = resolveOverlayId(command.target);
      if (overlay) {
        return {
          ok: true,
          command: command.id,
          surface: overlay,
          dispatched: [dispatch(OVERLAY_CLOSE_EVENT, { id: overlay })],
          mode: "shipping",
        };
      }
      const surface = resolveSurface(command.target);
      if (!surface) {
        return { ok: false, command: command.id, reason: `unknown surface: ${command.target}`, status: "invalid" };
      }
      return {
        ok: true,
        command: command.id,
        surface,
        dispatched: [dispatch("hosaka:close-app", { appId: surface })],
        mode: "shipping",
      };
    }
    case "ui.toggle_menu":
      return {
        ok: true,
        command: command.id,
        dispatched: [dispatch("hosaka:toggle-menu")],
        mode: "shipping",
      };
    case "ui.toggle_orb":
      return {
        ok: true,
        command: command.id,
        surface: "voice",
        dispatched: [dispatch("hosaka:open-app", { appId: "voice" })],
        mode: "shipping",
      };
    case "ui.toggle_chrome":
      return {
        ok: true,
        command: command.id,
        dispatched: [dispatch("hosaka:toggle-chrome")],
        mode: "shipping",
      };
    case "ui.focus_terminal":
      return {
        ok: true,
        command: command.id,
        surface: "terminal",
        dispatched: [
          dispatch("hosaka:focus-terminal"),
          dispatch(OVERLAY_CLOSE_ALL_EVENT, { keepPinned: true }),
        ],
        mode: "shipping",
      };
    case "ui.device_check": {
      const appId: AppId = command.kind === "mic"
        ? "device_mic"
        : command.kind === "cam" ? "device_cam" : "device_spk";
      return {
        ok: true,
        command: command.id,
        surface: appId,
        dispatched: [dispatch("hosaka:open-app", { appId })],
        mode: "shipping",
      };
    }
    case "ui.device_select": {
      const key = DEVICE_STORAGE[command.kind];
      try { localStorage.setItem(key, command.deviceId); } catch { /* quota */ }
      const kindMap = { mic: "audioinput", cam: "videoinput", spk: "audiooutput" } as const;
      return {
        ok: true,
        command: command.id,
        dispatched: [dispatch("hosaka:devicechange", { kind: kindMap[command.kind], deviceId: command.deviceId })],
        mode: "shipping",
      };
    }
    case "ui.show_diagnostics":
      return {
        ok: true,
        command: command.id,
        surface: "diag",
        dispatched: [dispatch(OVERLAY_OPEN_EVENT, { id: "diag" })],
        mode: "shipping",
      };
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
    case "ui.prefill_cmdline": {
      const text = String(command.text ?? "");
      if (!text) {
        return { ok: false, command: command.id, reason: "missing prefill text", status: "invalid" };
      }
      return {
        ok: true,
        command: command.id,
        dispatched: [
          dispatch("hosaka:cmdline-prefill", {
            text,
            submit: Boolean(command.submit),
            focus: command.focus !== false,
          }),
        ],
        mode: "shipping",
      };
    }
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

async function snapshotDeviceAgentPayload(kind: DeviceCheckKind): Promise<unknown> {
  // Lazy-imported so the shipped main bundle doesn't pay for the device
  // primitives unless the agent actually asks for a snapshot.
  const { buildDeviceAgentPayload } = await import("../panels/diagPrimitives");
  let devices: { deviceId: string; groupId: string; kind: MediaDeviceKind; label: string }[] = [];
  let permission: "unknown" | "granted" | "blocked" = "unknown";
  try {
    if (navigator.mediaDevices?.enumerateDevices) {
      const raw = await navigator.mediaDevices.enumerateDevices();
      devices = raw.map((d) => ({
        deviceId: d.deviceId,
        groupId: d.groupId,
        kind: d.kind,
        label: d.label || `${d.kind} (${d.deviceId.slice(0, 8)}…)`,
      }));
      if (devices.some((d) => d.label && !d.label.startsWith(d.kind))) permission = "granted";
    }
  } catch {
    // keep defaults
  }
  return buildDeviceAgentPayload(kind, { permission, devices });
}

const bridge: HosakaUiBridge = {
  execute: executeHosakaUiCommand,
  resolveSurface,
  listSurfaces: listHosakaSurfaces,
  snapshotDeviceAgentPayload,
};

if (typeof window !== "undefined") {
  window.hosakaUI = bridge;
}
