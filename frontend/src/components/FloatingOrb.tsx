/**
 * FloatingOrb — a persistent mini-orb that lives over every panel.
 *
 * - Listens for "hosaka:voice-state" events from VoicePanel.
 * - Tapping it fires "hosaka:open-tab" → "voice" so the operator can jump
 *   to voice mode from anywhere.
 * - Hidden when voice is already the active panel (passed as prop).
 * - Small footprint: pure CSS animation, no audio work here.
 */
import { useEffect, useRef, useState } from "react";

type VoiceVisualState =
  | "idle"
  | "live"
  | "listening"
  | "thinking"
  | "speaking"
  | "error"
  | "muted";

export function FloatingOrb({ voiceActive }: { voiceActive: boolean }) {
  const [vs, setVs] = useState<VoiceVisualState>("idle");
  const orbRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      const next = (e as CustomEvent<VoiceVisualState>).detail;
      if (next) setVs(next);
    };
    window.addEventListener("hosaka:voice-state", handler);
    return () => window.removeEventListener("hosaka:voice-state", handler);
  }, []);

  const openVoice = () => {
    window.dispatchEvent(new CustomEvent("hosaka:open-tab", { detail: "voice" }));
  };

  if (voiceActive) return null;

  return (
    <button
      ref={orbRef}
      className={`floating-orb floating-orb--${vs}`}
      onClick={openVoice}
      aria-label="open voice"
      title="voice"
    >
      <span className="floating-orb-ring" />
      <span className="floating-orb-orbit" aria-hidden="true">
        <span className="floating-orb-cross">+</span>
      </span>
      <span className="floating-orb-dot" />
    </button>
  );
}
