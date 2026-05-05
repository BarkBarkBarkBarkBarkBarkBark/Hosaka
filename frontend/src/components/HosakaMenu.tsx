import { useEffect, useMemo, useRef, useState } from "react";
import { Disclosure } from "./Disclosure";
import type { AppDefinition, AppId } from "../ui/appRegistry";
import { executeHosakaUiCommand } from "../ui/hosakaUi";
import {
  THEMES,
  applyTheme,
  getStoredTheme,
  getStoredOrbColor,
  getStoredOrbOrbit,
  setOrbColor,
  setOrbOrbit,
  type ThemeId,
} from "../ui/theme";

/**
 * HosakaMenu — sectioned discoverability hub.
 *
 * Sections (top → bottom):
 *   apps          · open windows + launchers + all apps
 *   voice & model · mode + cost picker shortcuts
 *   wifi          · live nmcli list with signal bars
 *   volume        · slash teach (no backend yet — degrades quietly)
 *   appearance    · 5 theme swatches + orb color/orbit
 *   quality       · low / high / auto orb compute
 *   diagnostics   · doctor / devices / wifi / system info shortcuts
 *   easter eggs   · /lore /plant /orb art
 *
 * Most rows route through `executeHosakaUiCommand({ id: "ui.prefill_cmdline" })`
 * so the user *sees* the slash command land in the cmdline. The menu becomes
 * a teaching surface for the keyboard-first UX rather than a parallel UI.
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

interface WifiNet {
  ssid: string;
  signal?: number | null;
  security?: string | null;
  active?: boolean;
  saved?: boolean;
  in_range?: boolean;
}

function bars(signal: number | null | undefined): string {
  if (signal == null) return "····";
  if (signal >= 75) return "▰▰▰▰";
  if (signal >= 50) return "▰▰▰▱";
  if (signal >= 25) return "▰▰▱▱";
  if (signal > 0)   return "▰▱▱▱";
  return "▱▱▱▱";
}

function suggest(text: string, opts?: { submit?: boolean }): void {
  executeHosakaUiCommand({
    id: "ui.prefill_cmdline",
    text,
    focus: true,
    submit: opts?.submit ?? false,
  });
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

  // ── live ui state ──────────────────────────────────────────
  const [theme, setTheme] = useState<ThemeId>(() => getStoredTheme());
  const [orbColor, setOrbColorState] = useState<string>(() => getStoredOrbColor() ?? "");
  const [orbOrbit, setOrbOrbitState] = useState<string>(() => getStoredOrbOrbit() ?? "");
  const [wifi, setWifi] = useState<WifiNet[] | null>(null);
  const [wifiLoading, setWifiLoading] = useState(false);
  const [wifiErr, setWifiErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
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

  // refresh wifi when menu opens
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setWifiLoading(true);
    setWifiErr(null);
    fetch("/api/v1/wifi/networks")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`http ${r.status}`))))
      .then((data: { networks?: WifiNet[] }) => {
        if (cancelled) return;
        const list = (data?.networks ?? []).slice().sort((a, b) => {
          if (!!b.active !== !!a.active) return b.active ? 1 : -1;
          return (b.signal ?? -1) - (a.signal ?? -1);
        });
        setWifi(list);
      })
      .catch((e) => { if (!cancelled) setWifiErr(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setWifiLoading(false); });
    return () => { cancelled = true; };
  }, [open]);

  // NB: keep all hooks above any early return — `useMemo` after `if (!open)
  // return null` would violate the rules-of-hooks and crash with
  // "Rendered more hooks than during the previous render".
  const orderedApps = useMemo(() => apps, [apps]);

  if (!open) return null;

  const pickApp = (appId: AppId) => { onSetActive(appId); onClose(); };

  const handleTheme = (id: ThemeId) => { setTheme(id); applyTheme(id); };
  const handleOrbColor = (v: string) => {
    setOrbColorState(v);
    setOrbColor(v.trim() ? v.trim() : null);
  };
  const handleOrbOrbit = (v: string) => {
    setOrbOrbitState(v);
    setOrbOrbit(v.trim() ? v.trim() : null);
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

        {/* ── apps ─────────────────────────────────────────── */}
        <Disclosure label="apps" glyph="◫" defaultOpen level={1}>
          {openAppIds.length > 0 && (
            <Disclosure label="open windows" glyph="◐" defaultOpen level={2}>
              <ul className="hosaka-menu-list">
                {openAppIds.map((appId) => {
                  const def = apps.find((a) => a.id === appId);
                  if (!def) return null;
                  return (
                    <li key={appId} className={`hosaka-menu-item ${activeAppId === appId ? "is-active" : ""}`}>
                      <button type="button" onClick={() => pickApp(appId)}>
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
          )}

          {launcherApps.length > 0 && (
            <Disclosure label="launch" glyph="▸" defaultOpen level={2}>
              <ul className="hosaka-menu-list">
                {launcherApps.map((app) => (
                  <li key={app.id} className={`hosaka-menu-item ${activeAppId === app.id ? "is-active" : ""}`}>
                    <button type="button" onClick={() => pickApp(app.id)}>
                      <span className="hosaka-menu-glyph">{app.glyph}</span>
                      <span>{app.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Disclosure>
          )}

          <Disclosure label="all apps" glyph="▤" level={2}>
            <ul className="hosaka-menu-list">
              {orderedApps.map((app) => (
                <li key={app.id} className={`hosaka-menu-item ${activeAppId === app.id ? "is-active" : ""}`}>
                  <button type="button" onClick={() => pickApp(app.id)}>
                    <span className="hosaka-menu-glyph">{app.glyph}</span>
                    <span>{app.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Disclosure>
        </Disclosure>

        {/* ── voice & model ────────────────────────────────── */}
        <Disclosure label="voice & model" glyph="◉" level={1}>
          <div className="hosaka-menu-pad">
            <p className="hosaka-menu-hint">single on/off lives in the voice panel. mode + cost picker here.</p>
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/voice mode agent", { submit: true })}>local agent · free</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/voice mode demo", { submit: true })}>openai realtime · paid</button>
            </div>
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/voice cam")}>camera</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/voice mic")}>microphone</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/voice spk")}>speaker</button>
            </div>
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/llm models")}>list models</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/llm config")}>llm config</button>
            </div>
          </div>
        </Disclosure>

        {/* ── wifi ─────────────────────────────────────────── */}
        <Disclosure label="wifi" glyph="≋" level={1}>
          <div className="hosaka-menu-pad">
            {wifiLoading && <p className="hosaka-menu-hint">scanning…</p>}
            {wifiErr && (
              <p className="hosaka-menu-hint hosaka-menu-hint--warn">
                wifi api unavailable. try <code>/wifi</code> in terminal.
              </p>
            )}
            {wifi && wifi.length === 0 && !wifiLoading && (
              <p className="hosaka-menu-hint">no networks visible.</p>
            )}
            {wifi && wifi.length > 0 && (
              <ul className="hosaka-wifi-list">
                {wifi.slice(0, 12).map((n) => (
                  <li key={n.ssid} className={`hosaka-wifi-item ${n.active ? "is-active" : ""}`}>
                    <button
                      type="button"
                      onClick={() => suggest(`/wifi connect ${n.ssid}`)}
                      title={n.security ?? "open"}
                    >
                      <span className="hosaka-wifi-bars" aria-hidden>{bars(n.signal)}</span>
                      <span className="hosaka-wifi-ssid">{n.ssid || "<hidden>"}</span>
                      <span className="hosaka-wifi-meta">
                        {n.active ? "● connected" : (n.saved ? "saved" : (n.security ? "🔒" : "open"))}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/wifi", { submit: true })}>refresh</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/wifi connect ")}>connect…</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/wifi forget ")}>forget…</button>
            </div>
          </div>
        </Disclosure>

        {/* ── volume ───────────────────────────────────────── */}
        <Disclosure label="volume" glyph="♪" level={1}>
          <div className="hosaka-menu-pad">
            <p className="hosaka-menu-hint">os mixer is the source of truth. these prefill terminal commands.</p>
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/volume mute", { submit: true })}>mute</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/volume 25", { submit: true })}>25%</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/volume 50", { submit: true })}>50%</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/volume 75", { submit: true })}>75%</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/volume 100", { submit: true })}>100%</button>
            </div>
          </div>
        </Disclosure>

        {/* ── appearance ───────────────────────────────────── */}
        <Disclosure label="appearance" glyph="✦" level={1}>
          <div className="hosaka-menu-pad">
            <p className="hosaka-menu-hint">theme</p>
            <div className="hosaka-theme-row">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`hosaka-theme-swatch theme-swatch--${t.id} ${theme === t.id ? "is-active" : ""}`}
                  onClick={() => handleTheme(t.id)}
                  title={t.hint}
                  aria-label={t.label}
                >
                  <span className="hosaka-theme-swatch-name">{t.label}</span>
                </button>
              ))}
            </div>

            <p className="hosaka-menu-hint">orb color (any css color, blank = theme default)</p>
            <div className="hosaka-menu-key">
              <input
                type="text"
                value={orbColor}
                placeholder="#ffbf46, deeppink, hsl(...)"
                onChange={(e) => handleOrbColor(e.target.value)}
                spellCheck={false}
              />
              <button type="button" className="hosaka-menu-chip" onClick={() => handleOrbColor("")}>reset</button>
            </div>

            <p className="hosaka-menu-hint">orbit text (chars ring the orb, max 24)</p>
            <div className="hosaka-menu-key">
              <input
                type="text"
                value={orbOrbit}
                maxLength={24}
                placeholder="HOSAKA · SIGNAL · STEADY"
                onChange={(e) => handleOrbOrbit(e.target.value)}
                spellCheck={false}
              />
              <button type="button" className="hosaka-menu-chip" onClick={() => handleOrbOrbit("")}>reset</button>
            </div>
          </div>
        </Disclosure>

        {/* ── quality ──────────────────────────────────────── */}
        <Disclosure label="quality" glyph="◇" level={1}>
          <div className="hosaka-menu-pad">
            <p className="hosaka-menu-hint">orb compute. low = ~25% gpu, kind to the pi.</p>
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/quality low", { submit: true })}>low</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/quality high", { submit: true })}>high</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/quality auto", { submit: true })}>auto</button>
            </div>
          </div>
        </Disclosure>

        {/* ── diagnostics ──────────────────────────────────── */}
        <Disclosure label="diagnostics" glyph="◈" level={1}>
          <div className="hosaka-menu-pad">
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/doctor", { submit: true })}>doctor</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/devices", { submit: true })}>devices</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/system", { submit: true })}>system info</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/wifi", { submit: true })}>wifi scan</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/help", { submit: true })}>help</button>
            </div>
          </div>
        </Disclosure>

        {/* ── easter eggs ──────────────────────────────────── */}
        <Disclosure label="easter eggs" glyph="✺" level={1}>
          <div className="hosaka-menu-pad">
            <div className="hosaka-menu-chip-row">
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/lore", { submit: true })}>lore</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/plant", { submit: true })}>plant</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/orb art", { submit: true })}>orb art</button>
              <button type="button" className="hosaka-menu-chip" onClick={() => suggest("/orb orbit HOSAKA · SIGNAL · STEADY", { submit: true })}>orbit text</button>
            </div>
          </div>
        </Disclosure>

        {settingsEnabled && (
          <div className="hosaka-menu-footer">
            <button
              type="button"
              className="hosaka-menu-settings"
              onClick={() => { onOpenSettings(); onClose(); }}
            >⚙ advanced settings</button>
          </div>
        )}
      </div>
    </div>
  );
}
