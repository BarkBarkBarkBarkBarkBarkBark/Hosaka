/**
 * FloatingOrb — a persistent mini-orb that lives over every panel.
 *
 * - Listens for "hosaka:voice-state" events from VoicePanel.
 * - Tapping it fires "hosaka:open-tab" → "voice".
 * - Hidden when voice is the active panel.
 *
 * Customization (via theme.ts helpers + CustomEvents):
 *   - localStorage `hosaka.orb.color`  — any CSS color, overrides theme accent
 *   - localStorage `hosaka.orb.orbit`  — single glyph or short string laid
 *     out around the ring (e.g. "+", "★", "hello")
 *   - localStorage `hosaka.orb.quality` — "low" | "high" (perf knob)
 *
 * Quality "low" disables the orbit + breath animation (Pi-friendly).
 */
import { useEffect, useRef, useState } from "react";
import { getStoredOrbColor, getStoredOrbOrbit } from "../ui/theme";

type VoiceVisualState =
  | "idle"
  | "live"
  | "listening"
  | "thinking"
  | "speaking"
  | "error"
  | "muted";

type Quality = "low" | "high";

function detectQuality(): Quality {
  try {
    const forced = localStorage.getItem("hosaka.orb.quality");
    if (forced === "low" || forced === "high") return forced;
  } catch { /* ignore */ }
  if (typeof window === "undefined") return "low";
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return "low";
  if (window.innerWidth <= 900 || window.innerHeight <= 540) return "low";
  return "high";
}

/** Lay characters out around a ring; cap so it never gets unreadable. */
function orbitChars(text: string): { ch: string; angle: number }[] {
  const chars = Array.from(text.slice(0, 24));
  if (chars.length === 0) return [];
  const step = 360 / chars.length;
  return chars.map((ch, i) => ({ ch, angle: i * step }));
}

export function FloatingOrb({ voiceActive }: { voiceActive: boolean }) {
  const [vs, setVs] = useState<VoiceVisualState>("idle");
  const [quality, setQuality] = useState<Quality>(() => detectQuality());
  const [color, setColor] = useState<string | null>(() => getStoredOrbColor());
  const [orbit, setOrbit] = useState<string>(() => getStoredOrbOrbit() ?? "+");
  const orbRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onVoice = (e: Event) => {
      const next = (e as CustomEvent<VoiceVisualState>).detail;
      if (next) setVs(next);
    };
    const onQuality = (e: Event) => {
      const next = (e as CustomEvent<Quality>).detail;
      if (next === "low" || next === "high") {
        setQuality(next);
        try { localStorage.setItem("hosaka.orb.quality", next); } catch { /* ignore */ }
      } else {
        setQuality(detectQuality());
      }
    };
    const onCustomize = (e: Event) => {
      const detail = (e as CustomEvent<{ color?: string; orbit?: string }>).detail || {};
      if ("color" in detail) setColor(detail.color ?? null);
      if ("orbit" in detail) setOrbit(detail.orbit ?? "+");
    };
    window.addEventListener("hosaka:voice-state", onVoice);
    window.addEventListener("hosaka:orb-quality", onQuality as EventListener);
    window.addEventListener("hosaka:orb-customize", onCustomize as EventListener);
    return () => {
      window.removeEventListener("hosaka:voice-state", onVoice);
      window.removeEventListener("hosaka:orb-quality", onQuality as EventListener);
      window.removeEventListener("hosaka:orb-customize", onCustomize as EventListener);
    };
  }, []);

  const openVoice = () => {
    window.dispatchEvent(new CustomEvent("hosaka:open-tab", { detail: "voice" }));
  };

  if (voiceActive) return null;

  // Operator-picked color overrides theme accent inline so it shows
  // up across all states without per-state CSS plumbing.
  const styleOverride = color
    ? ({
        ["--voice-accent" as string]: color,
        ["--voice-accent-strong" as string]: color,
        ["--voice-haze-strong" as string]: color,
      } as React.CSSProperties)
    : undefined;

  const chars = quality === "high" ? orbitChars(orbit) : [];
  const isText = chars.length > 1;
  const orbitClass = isText
    ? "floating-orb-orbit floating-orb-orbit--text"
    : "floating-orb-orbit";

  return (
    <button
      ref={orbRef}
      className={`floating-orb floating-orb--${vs} floating-orb--q-${quality}`}
      onClick={openVoice}
      aria-label="open voice"
      title="voice (Ctrl+O) · /orb to customize"
      data-hint="orb"
      style={styleOverride}
    >
      <span className="floating-orb-ring" />
      {chars.length > 0 && (
        <span className={orbitClass} aria-hidden="true">
          {isText ? (
            chars.map((c, i) => (
              <span
                key={i}
                className="floating-orb-glyph"
                style={{
                  transform: `rotate(${c.angle}deg) translateY(-30px) rotate(${-c.angle}deg)`,
                }}
              >
                {c.ch}
              </span>
            ))
          ) : (
            <span className="floating-orb-cross">{chars[0].ch}</span>
          )}
        </span>
      )}
      <span className="floating-orb-dot" />
    </button>
  );
}
