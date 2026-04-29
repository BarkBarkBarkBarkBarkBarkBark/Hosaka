// VoicePanel — speak-to-Hosaka mode.
//
// The panel orchestrates three browser APIs:
//   1. getUserMedia for the USB webcam (live preview <video>)
//   2. VoiceSession (WebRTC to OpenAI Realtime) for the audio I/O
//   3. BrowserWake (MicVAD) as an optional "always listening" trigger
//
// The Realtime session's own server-side VAD already detects turns, so
// the BrowserWake instance is really an "activate the session" trigger:
// when auto-listen is on, we open the session on first speech and leave
// it open. Otherwise the operator hits the big orb to start / stop.

import { useEffect, useMemo, useRef, useState } from "react";
import { VoiceSession, type VoiceState } from "../voice/realtimeClient";

type TranscriptItem = {
  id: string;
  role: "you" | "hosaka" | "tool";
  text: string;
};

type CamState = "off" | "starting" | "on" | "error";

function useWebcamPreview(active: boolean): {
  videoRef: React.RefObject<HTMLVideoElement>;
  state: CamState;
  error: string | null;
  retry: () => void;
} {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CamState>("off");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) {
      if (streamRef.current) {
        for (const t of streamRef.current.getTracks()) t.stop();
        streamRef.current = null;
      }
      setState("off");
      return;
    }
    let cancelled = false;
    setState("starting");
    setError(null);
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false,
        });
        if (cancelled) {
          for (const t of stream.getTracks()) t.stop();
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
        setState("on");
      } catch (exc) {
        if (cancelled) return;
        setError(String(exc));
        setState("error");
      }
    })();
    return () => {
      cancelled = true;
      if (streamRef.current) {
        for (const t of streamRef.current.getTracks()) t.stop();
        streamRef.current = null;
      }
    };
  }, [active, tick]);

  return { videoRef, state, error, retry: () => setTick((x) => x + 1) };
}

export function VoicePanel({ active }: { active: boolean }) {
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [camOn, setCamOn] = useState(true);
  const [cameraExpanded, setCameraExpanded] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const sessionRef = useRef<VoiceSession | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const { videoRef, state: camState, error: camError, retry: retryCam } =
    useWebcamPreview(active && camOn && cameraExpanded);

  const appendTranscript = (role: TranscriptItem["role"], text: string) => {
    setTranscript((t) => [
      ...t.slice(-49),
      { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, role, text },
    ]);
  };

  const startSession = async () => {
    if (sessionRef.current) return;
    setError(null);
    const sink = audioRef.current;
    if (!sink) return;
    const session = new VoiceSession({
      onState: (s) => setState(s),
      onError: (e) => setError(String((e as { message?: string })?.message ?? e)),
      onUserTranscript: (text) => appendTranscript("you", text),
      onAssistantTranscript: (delta) => {
        setTranscript((t) => {
          const last = t[t.length - 1];
          if (last && last.role === "hosaka") {
            return [...t.slice(0, -1), { ...last, text: last.text + delta }];
          }
          return [
            ...t.slice(-49),
            {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              role: "hosaka",
              text: delta,
            },
          ];
        });
      },
      onTool: (name, _args, output) => {
        appendTranscript("tool", `${name} → ${output}`);
        if (name === "todo_add") {
          try {
            window.dispatchEvent(
              new CustomEvent("hosaka:todo-add", { detail: extractTodoText(output) }),
            );
          } catch {/* noop */}
        }
      },
    });
    try {
      await session.start(sink);
      sessionRef.current = session;
      setSessionOpen(true);
    } catch (exc) {
      setError(String(exc));
      setState("error");
    }
  };

  const stopSession = async () => {
    const session = sessionRef.current;
    sessionRef.current = null;
    setSessionOpen(false);
    if (session) await session.stop();
    setState("idle");
  };

  useEffect(() => {
    return () => {
      sessionRef.current?.stop().catch(() => undefined);
      sessionRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!active && sessionRef.current) {
      void stopSession();
    }
  }, [active]);

  useEffect(() => {
    const el = transcriptRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [transcript, state]);

  const stateLabel = useMemo(() => {
    switch (state) {
      case "listening": return "listening";
      case "thinking":  return "thinking";
      case "speaking":  return "speaking";
      case "error":     return "error";
      default:          return sessionOpen ? "live" : "idle";
    }
  }, [state, sessionOpen]);

  const cameraStatus = useMemo(() => {
    if (!camOn) return "camera disabled";
    if (!cameraExpanded) return "camera parked";
    switch (camState) {
      case "on": return "camera live";
      case "starting": return "camera warming";
      case "error": return "camera error";
      default: return "camera off";
    }
  }, [camOn, camState, cameraExpanded]);

  return (
    <div className="voice-wrap">
      <header className="panel-header">
        <h2>
          <span className="panel-glyph">◎</span> voice
        </h2>
        <p className="panel-sub">
          talk to hosaka. this view is transcript-first: speak naturally, keep
          the history in sight, and expand the camera only when you need eyes.
        </p>
      </header>

      <div className="voice-layout">
        <section className="voice-main">
          {cameraExpanded && (
            <div className="voice-camera-panel">
              <div className="voice-camera-panel-head">
                <div>
                  <strong>camera</strong>
                  <span>
                    keep this parked until you want hosaka to look.
                  </span>
                </div>
                <div className="voice-camera-toolbar">
                  <label className="voice-camera-check">
                    <input
                      type="checkbox"
                      checked={camOn}
                      onChange={(e) => setCamOn(e.target.checked)}
                    />
                    camera enabled
                  </label>
                  <button className="btn btn-ghost" onClick={() => setCameraExpanded(false)}>
                    hide
                  </button>
                </div>
              </div>

              <div className="voice-camera voice-camera--expanded">
                <video ref={videoRef} className="voice-video" muted playsInline />
                {camState !== "on" && (
                  <div className="voice-camera-overlay">
                    {camState === "off" && "camera off"}
                    {camState === "starting" && "warming up camera…"}
                    {camState === "error" && (
                      <>
                        <div>camera error</div>
                        {camError && <small>{camError}</small>}
                        <button className="btn btn-ghost" onClick={retryCam}>retry</button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="voice-transcript-card">
            <div className="voice-transcript-head">
              <div className="voice-transcript-meta">
                <strong>live transcript</strong>
                <span>
                  {sessionOpen
                    ? `${stateLabel} · session open`
                    : "tap start listening and speak naturally"}
                </span>
              </div>
              <div className="voice-transcript-actions">
                <button
                  className="btn btn-ghost"
                  onClick={() => setTranscript([])}
                  disabled={transcript.length === 0}
                >
                  clear
                </button>
              </div>
            </div>

            <div ref={transcriptRef} className="voice-transcript" aria-live="polite">
              {transcript.length === 0 && (
                <p className="voice-empty">
                  transcript will appear here. say 'how are you', 'what do you see',
                  'add a todo: buy coffee', or 'ask the agent to show disk usage'.
                </p>
              )}
              {transcript.map((item) => (
                <div key={item.id} className={`voice-line voice-line--${item.role}`}>
                  <span className="voice-role">{item.role}</span>
                  <span className="voice-text">{item.text}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <aside className="voice-side">
          <div className="voice-status-card">
            <button
              className={`voice-orb voice-orb--${state}`}
              onClick={() => (sessionOpen ? stopSession() : startSession())}
              aria-label={sessionOpen ? "end voice session" : "start voice session"}
            >
              <span className="voice-orb-ring" />
              <span className="voice-orb-dot" />
            </button>
            <div className="voice-state-stack">
              <div className="voice-state-label">{stateLabel}</div>
              <div className="voice-state-sub">
                {sessionOpen ? "mic open · realtime link live" : "ready when you are"}
              </div>
            </div>
          </div>

          <div className="voice-controls-card">
            <button
              className="btn"
              onClick={() => (sessionOpen ? stopSession() : startSession())}
            >
              {sessionOpen ? "end session" : "start listening"}
            </button>

            <button
              className="btn btn-ghost"
              onClick={() => setCameraExpanded((v) => !v)}
            >
              {cameraExpanded ? "hide camera" : "show camera"}
            </button>

            <label className="voice-inline-toggle">
              <input
                type="checkbox"
                checked={camOn}
                onChange={(e) => setCamOn(e.target.checked)}
              />
              <span>camera enabled</span>
            </label>

            <div className="voice-camera-status">{cameraStatus}</div>

            {error && <div className="voice-error">{error}</div>}
          </div>

          <div className="voice-hint-card">
            <p>
              voice first. text stays center-stage so a new operator can talk,
              glance down, and trust the machine heard them.
            </p>
          </div>
        </aside>
      </div>

      <audio ref={audioRef} autoPlay />
    </div>
  );
}

function extractTodoText(output: string): string {
  const idx = output.toLowerCase().indexOf("added:");
  if (idx < 0) return output;
  return output.slice(idx + "added:".length).trim();
}
