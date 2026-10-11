import { useEffect, useState } from "react";
import type { AppDefinition, AppId } from "../ui/appRegistry";

type HosakaWindowBridge = {
  isKiosk?: boolean;
  toDesktop?: () => Promise<boolean>;
  toHosaka?: () => Promise<boolean>;
  toggle?: () => Promise<"desktop" | "hosaka">;
};

declare global {
  interface Window {
    hosakaWindow?: HosakaWindowBridge;
  }
}

export interface HosakaContextMenuProps {
  apps: AppDefinition[];
  onOpenApp: (appId: AppId) => void;
  onStageCommand: (command: string, autoSubmit?: boolean) => void;
}

type MenuState = {
  x: number;
  y: number;
};

function favoriteApp(apps: AppDefinition[]): AppId | null {
  let wanted = "";
  try {
    wanted = localStorage.getItem("hosaka.favoriteAppId") ?? "";
  } catch {
    wanted = "";
  }
  const match = apps.find((app) => app.id === wanted);
  return match?.id ?? apps.find((app) => app.id === "app_store")?.id ?? apps.find((app) => app.id === "home")?.id ?? null;
}

function allowNativeMenu(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  if (el.closest("input, textarea, select, [contenteditable='true'], .xterm")) return true;
  return false;
}

async function enterDeviceMode(): Promise<void> {
  if (!window.confirm("Enter device mode? This hides the kiosk and frees memory on the Pi.")) return;
  await fetch("/api/v1/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "device", persist: false }),
  });
}

export function HosakaContextMenu({ apps, onOpenApp, onStageCommand }: HosakaContextMenuProps) {
  const [menu, setMenu] = useState<MenuState | null>(null);

  useEffect(() => {
    const onContextMenu = (event: MouseEvent) => {
      if (allowNativeMenu(event.target)) return;
      event.preventDefault();
      const width = 260;
      const height = 280;
      setMenu({
        x: Math.min(event.clientX, window.innerWidth - width - 8),
        y: Math.min(event.clientY, window.innerHeight - height - 8),
      });
    };
    const close = () => setMenu(null);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(null);
    };
    window.addEventListener("contextmenu", onContextMenu);
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("contextmenu", onContextMenu);
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  if (!menu) return null;

  const run = (fn: () => void | Promise<void>) => {
    setMenu(null);
    void fn();
  };
  const favorite = favoriteApp(apps);

  return (
    <div
      className="hosaka-context-menu"
      role="menu"
      aria-label="Hosaka actions"
      style={{ left: menu.x, top: menu.y }}
      onClick={(event) => event.stopPropagation()}
    >
      <button type="button" role="menuitem" onClick={() => run(async () => { await window.hosakaWindow?.toHosaka?.(); })}>
        Return to Hosaka
      </button>
      <button type="button" role="menuitem" onClick={() => run(() => { if (favorite) onOpenApp(favorite); })}>
        Open favorite
      </button>
      <button type="button" role="menuitem" onClick={() => run(() => onOpenApp("app_store" as AppId))}>
        Applications
      </button>
      <button type="button" role="menuitem" onClick={() => run(() => onOpenApp("terminal" as AppId))}>
        Terminal
      </button>
      <hr />
      <button type="button" role="menuitem" onClick={() => run(async () => { await window.hosakaWindow?.toDesktop?.(); })}>
        Switch to LXQt desktop
      </button>
      <button type="button" role="menuitem" onClick={() => run(() => enterDeviceMode())}>
        Enter device mode
      </button>
      <button type="button" role="menuitem" onClick={() => run(() => onStageCommand("!hosaka-favorite", true))}>
        Open desktop favorite
      </button>
    </div>
  );
}
