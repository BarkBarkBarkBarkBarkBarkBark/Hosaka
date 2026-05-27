/**
 * VisualizerPanel — embeds the standalone "cascade" audio visualizer
 * (a separate Vite app living in the audio-visualizer/ sibling repo).
 *
 * Why an iframe and not an inline canvas?
 *
 *   - The visualizer is owned outside Hosaka and ships independently
 *     (deployed to Vercel/GH Pages). Iframing keeps it decoupled from the
 *     SPA build and avoids dragging Web Audio + canvas plumbing into this
 *     bundle.
 *   - The host can still drive it via postMessage. See
 *     audio-visualizer/src/main.ts for the protocol:
 *       { type: "cascade:set", scene, profile, source }
 *       { type: "cascade:hud", visible }
 *   - In hosaka embed mode (`?host=hosaka` or any framed load) the
 *     visualizer hides its own HUD; this panel renders the chrome instead.
 *
 * Dev: set VITE_VISUALIZER_URL=http://localhost:5174 (or run `npm run dev`
 * in audio-visualizer/ — that's the default port). Otherwise we fall back
 * to a known-good deployed URL placeholder.
 */

import { useEffect, useMemo, useRef, useState } from "react";

type Scene = { id: string; label: string };
type ReadyMsg = {
  type: "cascade:ready";
  version: string;
  scenes: Scene[];
  sources: Array<{ value: string; label: string }>;
};

const DEFAULT_DEV_URL = "http://localhost:5174";
const VISUALIZER_URL =
  (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_VISUALIZER_URL
  ?? DEFAULT_DEV_URL;

const FALLBACK_SCENES: Scene[] = [
  { id: "radial", label: "radial · fft spokes" },
  { id: "scope", label: "scope · lissajous" },
  { id: "eleven", label: "eleven · mandala" },
  { id: "cascade", label: "cascade · ifs fractal" },
  { id: "julia", label: "julia · subbass warp" },
  { id: "signal", label: "signal · grid + glitch" },
];

type Profile = "low" | "high";

function autoProfile(): Profile {
  if (typeof navigator === "undefined") return "low";
  const cores = navigator.hardwareConcurrency ?? 4;
  return cores <= 4 ? "low" : "high";
}

export function VisualizerPanel({ active }: { active: boolean }) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);
  const [scenes, setScenes] = useState<Scene[]>(FALLBACK_SCENES);
  const [sceneId, setSceneId] = useState<string>("radial");
  const [profile, setProfile] = useState<Profile>(autoProfile());

  const src = useMemo(() => {
    const url = new URL(VISUALIZER_URL);
    url.searchParams.set("host", "hosaka");
    url.searchParams.set("scene", sceneId);
    url.searchParams.set("profile", profile);
    return url.toString();
    // sceneId/profile changes are pushed via postMessage; this URL is only
    // re-used on initial mount or hard reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      const data = e.data as ReadyMsg | undefined;
      if (!data || typeof data !== "object" || data.type !== "cascade:ready") return;
      setReady(true);
      if (Array.isArray(data.scenes) && data.scenes.length) setScenes(data.scenes);
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // forward control changes to the iframe
  useEffect(() => {
    if (!ready) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "cascade:set", scene: sceneId, profile },
      "*",
    );
  }, [ready, sceneId, profile]);

  // pause when inactive — reload the iframe with audio off would be too
  // heavy; instead just blur the canvas so the operator notices it's idle.
  const dimmed = !active;

  return (
    <section className="panel visualizer-panel" aria-label="audio visualizer">
      <header className="visualizer-panel__bar">
        <span className="visualizer-panel__title">cascade</span>
        <div className="visualizer-panel__controls">
          <label>
            <span>scene</span>
            <select value={sceneId} onChange={(e) => setSceneId(e.target.value)}>
              {scenes.map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>cpu</span>
            <select value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
              <option value="low">low</option>
              <option value="high">high</option>
            </select>
          </label>
          <a className="visualizer-panel__pop" href={VISUALIZER_URL} target="_blank" rel="noreferrer">↗</a>
        </div>
      </header>
      <div className="visualizer-panel__stage" style={{ opacity: dimmed ? 0.4 : 1 }}>
        <iframe
          ref={iframeRef}
          src={src}
          title="cascade visualizer"
          allow="microphone; autoplay"
          // No sandbox — we trust this origin and we need mic+audio access.
        />
        {!ready && (
          <div className="visualizer-panel__loading">
            connecting to {VISUALIZER_URL}…<br />
            <small>run <code>npm run dev</code> in <code>audio-visualizer/</code> if this hangs.</small>
          </div>
        )}
      </div>
    </section>
  );
}
