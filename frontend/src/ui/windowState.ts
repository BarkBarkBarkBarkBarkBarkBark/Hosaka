import type { AppId } from "./appRegistry";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type WindowEntry = {
  appId: AppId;
  background: boolean;
  lastOpenedAt: number;
  lastFocusedAt: number;
  openCount: number;
  snapshot?: { [key: string]: JsonValue };
};

export type WindowsDoc = {
  activeAppId: AppId;
  chromeCollapsed: boolean;
  openAppIds: AppId[];
  windows: Partial<Record<AppId, WindowEntry>>;
  appState: Partial<Record<AppId, { [key: string]: JsonValue }>>;
};

export const INITIAL_WINDOWS_DOC: WindowsDoc = {
  activeAppId: "home",
  chromeCollapsed: false,
  openAppIds: ["home", "terminal"],
  windows: {
    home: {
      appId: "home",
      background: true,
      lastOpenedAt: 0,
      lastFocusedAt: 0,
      openCount: 1,
    },
    terminal: {
      appId: "terminal",
      background: false,
      lastOpenedAt: 0,
      lastFocusedAt: 0,
      openCount: 1,
    },
  },
  appState: {},
};

export function dedupeAppIds(appIds: AppId[]): AppId[] {
  return Array.from(new Set(appIds));
}
