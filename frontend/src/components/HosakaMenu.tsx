import { useEffect, useRef } from "react";
import { Disclosure } from "./Disclosure";
import type { AppDefinition, AppId } from "../ui/appRegistry";

/**
 * HosakaMenu — single-chevron, two-tier collapsible nav overlay.
 *
 * Replaces the visual surface of the dock + launchbar + window strip on
 * small screens / immersive mode. All actions still flow through the same
 * `setActiveApp` / `closeApp` callbacks, so `hosakaUi.ts` commands and the
 * `hosaka:*` event bus stay intact.
 */
export interface HosakaMenuProps {
  open: boolean;
  onClose: () => void;
  apps: AppDefinition[];
  launcherApps: AppDefinition[];
  openAppIds: AppId[];
  activeAppId: AppId;
  settingsEnabled: boolean;
  onSetActive: (appId: AppId) => void;
  onCloseApp: (appId: AppId) => void;
  onOpenSettings: () => void;
}

export function HosakaMenu({
  open,
  onClose,
  apps,
  launcherApps,
  openAppIds,
  activeAppId,
  settingsEnabled,
  onSetActive,
  onCloseApp,
  onOpenSettings,
}: HosakaMenuProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onClick = (e: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open, onClose]);

  if (!open) return null;

  const pick = (appId: AppId) => {
    onSetActive(appId);
    onClose();
  };

  return (
    <div className="hosaka-menu-scrim" role="dialog" aria-label="navigation">
      <div ref={ref} className="hosaka-menu">
        <div className="hosaka-menu-head">
          <span className="hosaka-menu-title">menu</span>
          <button
            type="button"
            className="hosaka-menu-close"
            onClick={onClose}
            aria-label="close menu"
          >✕</button>
        </div>

        <Disclosure label="windows" glyph="◫" defaultOpen level={1}>
          <ul className="hosaka-menu-list">
            {openAppIds.map((appId) => {
              const def = apps.find((a) => a.id === appId);
              if (!def) return null;
              return (
                <li key={appId} className={`hosaka-menu-item ${activeAppId === appId ? "is-active" : ""}`}>
                  <button type="button" onClick={() => pick(appId)}>
                    <span className="hosaka-menu-glyph">{def.glyph}</span>
                    <span>{def.title}</span>
                  </button>
                  {def.closable !== false && (
                    <button
                      type="button"
                      className="hosaka-menu-x"
                      aria-label={`close ${def.title}`}
                      onClick={(e) => { e.stopPropagation(); onCloseApp(appId); }}
                    >×</button>
                  )}
                </li>
              );
            })}
          </ul>
        </Disclosure>

        <Disclosure label="launch" glyph="▸" level={1}>
          <ul className="hosaka-menu-list">
            {launcherApps.map((app) => (
              <li key={app.id} className={`hosaka-menu-item ${activeAppId === app.id ? "is-active" : ""}`}>
                <button type="button" onClick={() => pick(app.id)}>
                  <span className="hosaka-menu-glyph">{app.glyph}</span>
                  <span>{app.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </Disclosure>

        <Disclosure label="all apps" glyph="▤" level={1}>
          <ul className="hosaka-menu-list">
            {apps.map((app) => (
              <li key={app.id} className={`hosaka-menu-item ${activeAppId === app.id ? "is-active" : ""}`}>
                <button type="button" onClick={() => pick(app.id)}>
                  <span className="hosaka-menu-glyph">{app.glyph}</span>
                  <span>{app.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </Disclosure>

        {settingsEnabled && (
          <div className="hosaka-menu-footer">
            <button
              type="button"
              className="hosaka-menu-settings"
              onClick={() => { onOpenSettings(); onClose(); }}
            >⚙ settings</button>
          </div>
        )}
      </div>
    </div>
  );
}
