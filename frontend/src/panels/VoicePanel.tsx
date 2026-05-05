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
import { appendConversationEntry } from "../chat/conversationLog";
import { DevicePanel, getPreferredMicConstraints, getPreferredSpeakerId } from "./DevicePanel";

type TranscriptItem = {
  id: string;
  role: "you" | "hosaka" | "tool" | "status";
  text: string;
};

type VoiceMode = "agent" | "demo";

let voiceAnalyserHardDisabled = false;

function shouldSkipLiveAnalyser(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const isSafari = /Safari/i.test(ua) && !/(Chrome|Chromium|CriOS|Edg|Electron)/i.test(ua);
  // Safari/WebKit has been throwing during AudioContext + MediaStream analyser
  // setup under React dev StrictMode. The analyser is decorative/local-only;
  // never let it take down the renderer. Electron/Chromium keeps the live glow.
  return isSafari;
}

type AgentJobCreateOut = {
  ok: boolean;
  job_id: string;
  status: string;
  spoken_text?: string;
  internal_note?: string;
  used_backend?: string;
};

type AgentJobOut = {
  ok: boolean;
  job_id: string;
  status: string;
  operator_text: string;
  spoken_text: string;
  internal_note?: string;
  used_backend?: string;
  error?: string;
  done: boolean;
};

type VoiceHealth = {
  public_mode?: boolean;
};

type CamState = "off" | "starting" | "on" | "error";

function getPreferredRecordingMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const options = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return options.find((value) => MediaRecorder.isTypeSupported(value));
}

/** Strip codec params from a mime type: "audio/webm;codecs=opus" → "audio/webm" */
function bareAudioType(blobType: string): string {
  return (blobType || "audio/webm").split(";")[0].trim().toLowerCase();
}

function audioExt(bareType: string): string {
  if (bareType.includes("mp4")) return "m4a";
  if (bareType.includes("ogg")) return "ogg";
  if (bareType.includes("mpeg") || bareType.includes("mpga")) return "mp3";
  if (bareType.includes("wav")) return "wav";
  return "webm";
}

async function createAgentTurnJob(blob: Blob): Promise<AgentJobCreateOut> {
  const form = new FormData();
  const bare = bareAudioType(blob.type);
  const ext = audioExt(bare);
  // Create a new blob with a clean content-type so the server receives the bare type.
  const cleanBlob = new Blob([blob], { type: bare });
  form.append("audio", cleanBlob, `hosaka-turn.${ext}`);

  const resp = await fetch("/api/v1/voice/agent-jobs", {
    method: "POST",
    body: form,
  });
  if (!resp.ok) {
    let detail = "";
    try {
      const payload = (await resp.json()) as { detail?: string };
      detail = String(payload.detail ?? "").trim();
    } catch {
      detail = (await resp.text().catch(() => "")).trim();
    }
    throw new Error(detail || `agent-jobs ${resp.status}`);
  }
  return (await resp.json()) as AgentJobCreateOut;
}

async function readAgentTurnJob(jobId: string): Promise<AgentJobOut> {
  const resp = await fetch(`/api/v1/voice/agent-jobs/${jobId}`);
  if (!resp.ok) {
    let detail = "";
    try {
      const payload = (await resp.json()) as { detail?: string };
      detail = String(payload.detail ?? "").trim();
    } catch {
      detail = (await resp.text().catch(() => "")).trim();
    }
    throw new Error(detail || `agent-job ${resp.status}`);
  }
  return (await resp.json()) as AgentJobOut;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function mapJobStatusToPhase(status: string): "uploading" | "transcribing" | "thinking" {
  switch (status) {
    case "queued":
      return "uploading";
    case "transcribing":
      return "transcribing";
    default:
      return "thinking";
  }
}

function playCompletionDing() {
  const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return;
  const ctx = new AudioCtx();
  const now = ctx.currentTime;
  const master = ctx.createGain();
  master.gain.setValueAtTime(0.0001, now);
  master.gain.exponentialRampToValueAtTime(0.05, now + 0.01);
  master.gain.exponentialRampToValueAtTime(0.0001, now + 0.42);
  master.connect(ctx.destination);

  for (const [offset, freq] of [[0, 880], [0.08, 1320]] as const) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, now + offset);
    gain.gain.setValueAtTime(0.0001, now + offset);
    gain.gain.exponentialRampToValueAtTime(0.18, now + offset + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.18);
    osc.connect(gain);
    gain.connect(master);
    osc.start(now + offset);
    osc.stop(now + offset + 0.2);
  }

  window.setTimeout(() => {
    void ctx.close().catch(() => undefined);
  }, 700);
}

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

/**
 * Reads RMS from a MediaStream via Web Audio at 60 fps, EMA-smoothed.
 * Returns a normalised 0–1 value (0 = silence / –60 dB, 1 = peak / –10 dB).
 * Attaches a CSS custom-property writer to an optional orb element:
 *   --v-scale   ring radius multiplier   (1.0 – 1.55)
 *   --v-glow    raw level                (0.0 – 1.0)
 *   --v-speed   animation speed factor   (1.0 – 2.0)
 *   --v-bright  sigmoid-shaped brightness (0.0 – 1.0)
 *                  -> ramps fast around the "present" threshold so the orb
 *                     visibly lights up as soon as the operator speaks.
 *   --v-hue     0 quiet → 1 present → 2 loud (smoothstep'd)
 *                  -> CSS reads it to shift filter / colour by threshold.
 */
function useVoiceAnalyser(
  stream: MediaStream | null,
  orbEl: HTMLElement | null,
): number {
  const smoothRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AnalyserNode | null>(null);
  const bufRef = useRef<Float32Array>(new Float32Array(256));
  const [level, setLevel] = useState(0);

  // Sigmoid: steep ramp around `mid`. k controls steepness.
  const sigmoid = (x: number, mid: number, k: number) =>
    1 / (1 + Math.exp(-k * (x - mid)));
  // Smoothstep between two thresholds, returns 0..1.
  const smoothstep = (x: number, a: number, b: number) => {
    const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  };
  // Two thresholds:
  //   QUIET→PRESENT around 0.18 (a normal speaking voice clears this fast)
  //   PRESENT→LOUD around 0.55 (shouting / sustained energy)
  // hue value: 0 in silence, 1 once present, 2 once loud.
  const computeHue = (v: number) =>
    smoothstep(v, 0.10, 0.26) + smoothstep(v, 0.45, 0.65);

  const writeOrbVars = (v: number) => {
    if (!orbEl) return;
    const bright = sigmoid(v, 0.22, 14);
    const hue = computeHue(v);
    orbEl.style.setProperty("--v-scale", String(1 + v * 0.55));
    orbEl.style.setProperty("--v-glow", String(v));
    orbEl.style.setProperty("--v-speed", String(1 + v));
    orbEl.style.setProperty("--v-bright", String(bright));
    orbEl.style.setProperty("--v-hue", String(hue));
  };

  useEffect(() => {
    if (shouldSkipLiveAnalyser()) {
      voiceAnalyserHardDisabled = true;
      writeOrbVars(0);
      setLevel(0);
      return;
    }
    if (voiceAnalyserHardDisabled) return;
    try {
    if (!stream) {
      // fade out smoothly when stream disappears
      let cancelled = false;
      const fade = () => {
        if (cancelled) return;
        smoothRef.current *= 0.85;
        const v = smoothRef.current;
        writeOrbVars(v);
        setLevel(v);
        if (v > 0.001 && rafRef.current !== null) {
          rafRef.current = requestAnimationFrame(fade);
        } else {
          rafRef.current = null;
        }
      };
      if (rafRef.current === null) rafRef.current = requestAnimationFrame(fade);
      return () => {
        cancelled = true;
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current);
          rafRef.current = null;
        }
      };
    }

    let cancelled = false;
    const AudioCtx = window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    let ctx: AudioContext;
    let analyser: AnalyserNode;
    let source: MediaStreamAudioSourceNode;
    try {
      ctx = new AudioCtx();
      analyser = ctx.createAnalyser();
      source = ctx.createMediaStreamSource(stream);
    } catch (error) {
      console.warn("voice analyser unavailable", error);
      return;
    }
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0; // we do our own EMA
    const buf = new Float32Array(analyser.fftSize);
    bufRef.current = buf;
    ctxRef.current = ctx;
    nodeRef.current = analyser;

    try { source.connect(analyser); } catch (error) {
      console.warn("voice analyser connect failed", error);
      void ctx.close().catch(() => undefined);
      ctxRef.current = null;
      nodeRef.current = null;
      return;
    }

    // EMA alpha ≈ 1 – e^(–1/(fps*tau)) with tau≈0.08s → alpha≈0.13 at 60fps
    const ALPHA = 0.13;
    const DB_FLOOR = -60;
    const DB_CEIL = -10;

    // Browsers suspend AudioContext until the user has interacted with the page.
    // Resume defensively: some WebKit builds can throw or return undefined.
    try {
      void ctx.resume()?.catch?.(() => undefined);
    } catch {
      // leave suspended; the visualizer will retry naturally on the next frame
    }

    const tick = () => {
      if (cancelled) return;
      // Re-check suspension each frame — context becomes running after first gesture.
      if (ctx.state === "suspended") {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      try {
        analyser.getFloatTimeDomainData(buf);
      } catch (error) {
        console.warn("voice analyser tick failed", error);
        rafRef.current = null;
        return;
      }
      let sq = 0;
      for (let i = 0; i < buf.length; i++) sq += buf[i] * buf[i];
      const rms = Math.sqrt(sq / buf.length);
      const db = rms < 1e-9 ? DB_FLOOR : 20 * Math.log10(rms);
      const raw = Math.max(0, Math.min(1, (db - DB_FLOOR) / (DB_CEIL - DB_FLOOR)));
      smoothRef.current = ALPHA * raw + (1 - ALPHA) * smoothRef.current;
      const v = smoothRef.current;
      writeOrbVars(v);
      setLevel(v);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
      try { source.disconnect(); } catch {/* noop */}
      try { void ctx.close()?.catch?.(() => undefined); } catch { /* noop */ }
      ctxRef.current = null;
      nodeRef.current = null;
    };
    } catch (error) {
      voiceAnalyserHardDisabled = true;
      console.warn("voice analyser disabled after setup failure", error);
      if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
      try { ctxRef.current?.close().catch(() => undefined); } catch { /* noop */ }
      ctxRef.current = null;
      nodeRef.current = null;
      return;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream, orbEl]);

  return level;
}

/** Keeps a mic stream open as long as the panel is active + not muted. */
function usePersistentMic(active: boolean, muted: boolean): MediaStream | null {
  const [stream, setStream] = useState<MediaStream | null>(null);

  // Re-open stream when device preference changes.
  const [deviceKey, setDeviceKey] = useState(0);
  useEffect(() => {
    const onDeviceChange = (e: Event) => {
      const detail = (e as CustomEvent<{ kind: string }>).detail;
      if (detail?.kind === "audioinput") setDeviceKey((k) => k + 1);
    };
    window.addEventListener("hosaka:devicechange", onDeviceChange);
    return () => window.removeEventListener("hosaka:devicechange", onDeviceChange);
  }, []);

  useEffect(() => {
    if (!active || muted) {
      setStream((prev) => {
        if (prev) for (const t of prev.getTracks()) t.stop();
        return null;
      });
      return;
    }
    let cancelled = false;
    navigator.mediaDevices.getUserMedia({
      audio: getPreferredMicConstraints(),
    }).then((s) => {
      if (cancelled) { for (const t of s.getTracks()) t.stop(); return; }
      setStream(s);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
      setStream((prev) => {
        if (prev) for (const t of prev.getTracks()) t.stop();
        return null;
      });
    };
  }, [active, muted, deviceKey]);
  return stream;
}

/**
 * Energy-based VAD. Polls mic stream at 50 ms intervals.
 * Calls onSpeechStart after SPEECH_ONSET_MS of audio above threshold.
 * Calls onSpeechEnd  after SILENCE_END_MS  of silence below threshold.
 * Callbacks are held in refs so callers can pass fresh closures each render.
 */
function useVAD(
  stream: MediaStream | null,
  onSpeechStart: () => void,
  onSpeechEnd: () => void,
  enabled: boolean,
) {
  const startRef = useRef(onSpeechStart);
  const endRef   = useRef(onSpeechEnd);
  startRef.current = onSpeechStart;
  endRef.current   = onSpeechEnd;

  useEffect(() => {
    if (!stream || !enabled) return;
    const AudioCtx = window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx      = new AudioCtx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    const buf    = new Float32Array(analyser.fftSize);
    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);
    ctx.resume().catch(() => undefined);

    const SPEECH_THRESHOLD = 0.08;   // RMS above → speech
    const SILENCE_THRESHOLD = 0.035; // RMS below → silence
    const SPEECH_ONSET_MS = 160;     // must sustain before firing onSpeechStart
    const SILENCE_END_MS  = 2200;    // must sustain before firing onSpeechEnd
    const TICK_MS = 50;

    let speechMs  = 0;
    let silenceMs = 0;
    let speaking  = false;
    let stopped   = false;
    let timerId   = 0;

    const tick = () => {
      if (stopped) return;
      analyser.getFloatTimeDomainData(buf);
      let sq = 0;
      for (let i = 0; i < buf.length; i++) sq += buf[i] * buf[i];
      const rms = Math.sqrt(sq / buf.length);

      if (rms > SPEECH_THRESHOLD) {
        speechMs  += TICK_MS;
        silenceMs  = 0;
        if (!speaking && speechMs >= SPEECH_ONSET_MS) {
          speaking = true;
          startRef.current();
        }
      } else if (rms < SILENCE_THRESHOLD) {
        silenceMs += TICK_MS;
        speechMs   = 0;
        if (speaking && silenceMs >= SILENCE_END_MS) {
          speaking  = false;
          silenceMs = 0;
          endRef.current();
        }
      } else {
        speechMs = 0; // dead zone — don't accumulate onset credit
      }
      timerId = window.setTimeout(tick, TICK_MS);
    };
    timerId = window.setTimeout(tick, TICK_MS);

    return () => {
      stopped = true;
      window.clearTimeout(timerId);
      try { source.disconnect(); } catch {/* noop */}
      ctx.close().catch(() => undefined);
    };
  }, [stream, enabled]);
}

/** Speak text aloud via Web Speech API. Cancels any current utterance first. */
function speakText(text: string) {
  if (typeof speechSynthesis === "undefined") return;
  speechSynthesis.cancel();
  if (!text.trim()) return;
  const utt = new SpeechSynthesisUtterance(text.trim());
  // Prefer a natural-sounding voice if available
  const voices = speechSynthesis.getVoices();
  const preferred = voices.find((v) =>
    v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Samantha") || v.name.includes("Google") || v.name.includes("Karen"))
  ) ?? voices.find((v) => v.lang.startsWith("en"));
  if (preferred) utt.voice = preferred;
  utt.rate  = 0.97;
  utt.pitch = 1.0;
  utt.volume = 0.88;
  speechSynthesis.speak(utt);
}

export function VoicePanel({ active }: { active: boolean }) {
  const maxTranscriptItems = 200;
  const [mode, setMode] = useState<VoiceMode>(() => {
    try {
      return localStorage.getItem("hosaka.voiceMode") === "demo" ? "demo" : "agent";
    } catch {
      return "agent";
    }
  });
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [camOn, setCamOn] = useState(true);
  const [cameraExpanded, setCameraExpanded] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [followTranscript, setFollowTranscript] = useState(true);
  const [agentRecording, setAgentRecording] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentPhase, setAgentPhase] = useState<"idle" | "recording" | "uploading" | "transcribing" | "thinking">("idle");
  const [, setPublicMode] = useState(false);
  // Orb-first mode: orb fills the screen, drawer slides up for transcript + controls.
  // Default to orb-first on narrow viewports.
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Full-screen orb mode: opt-in for the current session only. Do not persist
  // it; a stale localStorage flag previously made reloads look like a black
  // screen because the full-viewport orb overlay came back before context.
  const [fullOrb, setFullOrb] = useState(false);
  useEffect(() => {
    try { window.localStorage.removeItem("hosaka.voice.fullOrb"); } catch { /* noop */ }
  }, []);
  // Auto-engage fullOrb on small / kiosk viewports the first time the panel
  // becomes active. Aesthetic only — does not change session/agent state.
  useEffect(() => {
    if (!active || fullOrb) return;
    try {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const small = w <= 900 || (w <= 820 && h <= 500);
      if (small) setFullOrb(true);
    } catch { /* noop */ }
    // run once per activation only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
  // Esc exits fullscreen orb (or closes the drawer first if it's open).
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (drawerOpen) { setDrawerOpen(false); return; }
      if (fullOrb) { setFullOrb(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, drawerOpen, fullOrb]);
  const sessionRef = useRef<VoiceSession | null>(null);
  const agentRecorderRef = useRef<MediaRecorder | null>(null);
  const agentStreamRef = useRef<MediaStream | null>(null);
  const agentChunksRef = useRef<Blob[]>([]);
  const agentRunNonceRef = useRef(0);
  const speakingResetRef = useRef<number | null>(null);
  // Cooldown: block VAD re-trigger for N ms after a turn completes.
  const cooldownUntilRef = useRef<number>(0);
  const audioRef = useRef<HTMLAudioElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  // Callback ref: stored in state so useVoiceAnalyser re-runs when the orb mounts.
  const [orbEl, setOrbEl] = useState<HTMLButtonElement | null>(null);
  const [muted] = useState(false);
  // Live caption: last 2 visible transcript items for orb overlay
  const [liveCaption, setLiveCaption] = useState<TranscriptItem[]>([]);

  // Local analyser mic — open while the panel is active so the orb can breathe
  // with the room/operator without starting an OpenAI realtime session or an
  // agent turn. API calls only happen after an explicit press-to-talk action.
  const micStream = usePersistentMic(active, false);
  // Ref so closures (VAD callbacks, startAgentRecording) always see the latest stream.
  const micStreamRef = useRef<MediaStream | null>(null);
  micStreamRef.current = micStream;

  // Feed the persistent stream to the orb visualiser (always-on mic reactivity).
  useVoiceAnalyser(micStream, orbEl);

  // Apply speaker preference to the audio element whenever it changes.
  useEffect(() => {
    const apply = () => {
      const el = audioRef.current;
      if (!el) return;
      const id = getPreferredSpeakerId();
      if (id && id !== "default") {
        const e = el as HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> };
        e.setSinkId?.(id).catch(() => undefined);
      }
    };
    apply();
    window.addEventListener("hosaka:devicechange", apply);
    return () => window.removeEventListener("hosaka:devicechange", apply);
  }, []);

  const { videoRef, state: camState, error: camError, retry: retryCam } =
    useWebcamPreview(active && camOn && cameraExpanded);

  const appendTranscript = (role: TranscriptItem["role"], text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setTranscript((t) => [
      ...t.slice(-(maxTranscriptItems - 1)),
      { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, role, text: trimmed },
    ]);
    appendConversationEntry({
      role: role === "you" ? "user" : role === "hosaka" ? "assistant" : role === "tool" ? "tool" : "system",
      source: mode === "agent" ? "agent" : "voice",
      channel: role === "status" ? "system" : "voice",
      text: trimmed,
      visibility: role === "status" || role === "tool" ? "hidden" : "visible",
      appId: "voice",
    });
  };

  const clearSpeakingReset = () => {
    if (speakingResetRef.current !== null) {
      window.clearTimeout(speakingResetRef.current);
      speakingResetRef.current = null;
    }
  };

  const pulseSpokenReply = () => {
    clearSpeakingReset();
    setState("speaking");
    speakingResetRef.current = window.setTimeout(() => {
      setState("idle");
      speakingResetRef.current = null;
    }, 900);
  };

  const resetAgentRecorder = () => {
    agentRecorderRef.current = null;
    agentChunksRef.current = [];
    agentStreamRef.current = null;
  };

  const startSession = async () => {
    if (mode !== "demo") return;
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
            ...t.slice(-(maxTranscriptItems - 1)),
            {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              role: "hosaka",
              text: delta,
            },
          ];
        });
      },
      onAssistantTranscriptDone: (text) => {
        appendConversationEntry({
          role: "assistant",
          source: "voice",
          channel: "voice",
          text,
          visibility: "visible",
          appId: "voice",
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

  const startAgentRecording = async () => {
    if (mode !== "agent") return;
    if (agentBusy || agentRecording) return;
    if (Date.now() < cooldownUntilRef.current) return;  // post-turn cooldown
    setError(null);
    clearSpeakingReset();
    try {
      // Prefer the persistent stream; fall back to getUserMedia if not yet open.
      const stream = micStreamRef.current ?? await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      agentStreamRef.current = stream;
      agentChunksRef.current = [];
      const mimeType = getPreferredRecordingMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) agentChunksRef.current.push(event.data);
      };
      recorder.start(200);
      agentRecorderRef.current = recorder;
      setAgentRecording(true);
      setAgentPhase("recording");
      setSessionOpen(true);
      setState("listening");
    } catch (exc) {
      resetAgentRecorder();
      setAgentPhase("idle");
      setError(String(exc));
      setState("error");
    }
  };

  const stopAgentRecording = async () => {
    const recorder = agentRecorderRef.current;
    if (!recorder) return;
    const runNonce = ++agentRunNonceRef.current;
    setAgentRecording(false);
    setSessionOpen(false);
    setAgentBusy(true);
    setAgentPhase("uploading");
    setState("thinking");

    try {
      const blob = await new Promise<Blob>((resolve, reject) => {
        const type = recorder.mimeType || getPreferredRecordingMimeType() || "audio/webm";
        recorder.onerror = () => reject(new Error("recording failed"));
        recorder.onstop = () => resolve(new Blob(agentChunksRef.current, { type }));
        recorder.stop();
      });
      resetAgentRecorder();

      // Empty or near-empty blob → Whisper returns 400. Skip submission.
      if (blob.size < 4000) {
        appendTranscript("status", "no audio detected — try speaking closer to the mic");
        setAgentBusy(false);
        setAgentPhase("idle");
        setState("idle");
        return;
      }

      const job = await createAgentTurnJob(blob);
      if (agentRunNonceRef.current !== runNonce) return;

      if (job.spoken_text) appendTranscript("hosaka", job.spoken_text);
      if (job.internal_note) appendTranscript("status", job.internal_note);
      setAgentPhase(mapJobStatusToPhase(job.status));

      let sawOperator = false;
      let lastInternalNote = String(job.internal_note ?? "").trim();
      let result: AgentJobOut;

      for (;;) {
        await sleep(850);
        if (agentRunNonceRef.current !== runNonce) return;
        result = await readAgentTurnJob(job.job_id);
        if (agentRunNonceRef.current !== runNonce) return;
        if (!result.done) {
          setAgentPhase(mapJobStatusToPhase(result.status));
          const nextNote = String(result.internal_note ?? "").trim();
          if (nextNote && nextNote !== lastInternalNote) {
            appendTranscript("status", nextNote);
            lastInternalNote = nextNote;
          }
          if (result.operator_text && !sawOperator) {
            appendTranscript("you", result.operator_text);
            sawOperator = true;
          }
          continue;
        }

        if (result.operator_text && !sawOperator) appendTranscript("you", result.operator_text);
        if (result.internal_note) appendTranscript("status", result.internal_note);
        if (result.error) appendTranscript("status", result.error);
        if (result.spoken_text) {
          appendTranscript("hosaka", result.spoken_text);
          speakText(result.spoken_text);
          playCompletionDing();
          pulseSpokenReply();
        } else {
          setState("idle");
        }
        break;
      }
      setAgentPhase("idle");
    } catch (exc) {
      resetAgentRecorder();
      setAgentPhase("idle");
      setError(String(exc));
      setState("error");
    } finally {
      setAgentBusy(false);
      // 3-second cooldown so VAD can't fire again immediately after a turn.
      cooldownUntilRef.current = Date.now() + 3000;
    }
  };

  const toggleVoiceTurn = () => {
    if (mode === "demo") {
      return sessionOpen ? void stopSession() : void startSession();
    }
    return agentRecording ? void stopAgentRecording() : void startAgentRecording();
  };

  useEffect(() => {
    return () => {
      agentRunNonceRef.current += 1;
      clearSpeakingReset();
      sessionRef.current?.stop().catch(() => undefined);
      sessionRef.current = null;
      const recorder = agentRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        try { recorder.stop(); } catch {/* noop */}
      }
      resetAgentRecorder();
    };
  }, []);

  useEffect(() => {
    if (!active) {
      if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
      agentRunNonceRef.current += 1;
      if (sessionRef.current) {
        void stopSession();
      }
      if (agentRecorderRef.current && agentRecorderRef.current.state !== "inactive") {
        try { agentRecorderRef.current.stop(); } catch {/* noop */}
      }
      resetAgentRecorder();
      setAgentRecording(false);
      setAgentBusy(false);
      setAgentPhase("idle");
    }
  }, [active]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => r.json())
      .then((payload: VoiceHealth) => {
        if (cancelled) return;
        const nextPublicMode = Boolean(payload.public_mode);
        setPublicMode(nextPublicMode);
        if (nextPublicMode) setMode("demo");
      })
      .catch(() => {
        if (!cancelled) setPublicMode(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem("hosaka.voiceMode", mode);
    } catch {/* noop */}
  }, [mode]);

  useEffect(() => {
    if (mode !== "agent" && agentRecording) {
      void stopAgentRecording();
    }
  }, [agentRecording, mode]);

  useEffect(() => {
    if (mode !== "demo" && sessionRef.current) {
      void stopSession();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    if (mode !== "agent") {
      agentRunNonceRef.current += 1;
      setAgentBusy(false);
      setAgentPhase("idle");
    }
  }, [mode]);

  // Press-to-talk only. VAD used to auto-start turns when speech was detected,
  // which burned API calls on room noise. Keep the analyser live for visuals,
  // but never submit audio unless the operator presses start/stop.
  useVAD(
    micStream,
    () => { void startAgentRecording(); },
    () => { void stopAgentRecording(); },
    false,
  );

  // Keep last 3 non-status lines for the full-orb caption overlay
  useEffect(() => {
    const visible = transcript.filter((t) => t.role !== "status" && t.role !== "tool");
    setLiveCaption(visible.slice(-3));
  }, [transcript]);

  useEffect(() => {
    const el = transcriptRef.current;
    if (!el || !followTranscript) return;
    el.scrollTop = el.scrollHeight;
  }, [followTranscript, transcript, state]);

  const handleTranscriptScroll = () => {
    const el = transcriptRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setFollowTranscript(distanceFromBottom < 20);
  };

  const jumpToLatest = () => {
    const el = transcriptRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setFollowTranscript(true);
  };

  const stateLabel = useMemo(() => {
    if (mode === "agent") {
      if (muted) return "muted";
      if (agentBusy) return "thinking";
      if (agentRecording) return "listening";
      if (micStream) return "ready";
    }
    switch (state) {
      case "listening": return "listening";
      case "thinking":  return "thinking";
      case "speaking":  return "speaking";
      case "error":     return "error";
      default:          return sessionOpen ? "live" : "idle";
    }
  }, [agentBusy, agentRecording, muted, micStream, mode, state, sessionOpen]);

  const visualState = muted && mode === "agent"
    ? "muted"
    : mode === "agent"
      ? (agentBusy ? "thinking" : agentRecording ? "listening" : micStream ? "live" : state)
      : (state === "idle" ? (sessionOpen ? "live" : "idle") : state);

  // Broadcast so FloatingOrb in the App shell can mirror voice state.
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("hosaka:voice-state", { detail: visualState }),
    );
  }, [visualState]);

  const agentPhaseLabel = useMemo(() => {
    switch (agentPhase) {
      case "recording": return "recording · press stop to send";
      case "uploading": return "packaging the turn";
      case "transcribing": return "whisper is transcribing";
      case "thinking": return "picoclaw is working";
      default: return "press start to send one turn";
    }
  }, [agentPhase]);

  const statusSub = mode === "agent"
    ? muted
      ? "tap to unmute"
      : agentRecording
        ? "recording · press stop to send"
        : agentBusy
          ? agentPhaseLabel
          : micStream
            ? "orb is local-only · no API until start"
            : "opening mic…"
    : sessionOpen
      ? "realtime session live · press stop to close"
      : micStream
        ? "orb is local-only · press start for realtime"
        : "opening mic…";

  if (fullOrb) {
    return (
      <div className={`voice-fullscreen voice-fullscreen--${visualState}`}>
        {/* Full-screen ambient haze */}
        <div className="voice-fullscreen-haze" aria-hidden="true" />

        {/* The orb — fills most of the screen */}
        <button
          ref={setOrbEl}
          className={`voice-orb voice-orb--full voice-orb--${visualState}`}
          onClick={toggleVoiceTurn}
          onContextMenu={(e) => e.preventDefault()}
          aria-label={sessionOpen || agentRecording ? "stop voice session" : "start voice session"}
        >
          <span className="voice-orb-ring" />
          <span className="voice-jupiter-ring voice-jupiter-ring--a" aria-hidden="true" />
          <span className="voice-jupiter-ring voice-jupiter-ring--b" aria-hidden="true" />
          <span className="voice-orbit voice-orbit--1" aria-hidden="true">
            <span className="voice-orbit-cross">+</span>
          </span>
          <span className="voice-orbit voice-orbit--2" aria-hidden="true">
            <span className="voice-orbit-cross">+</span>
          </span>
          <span className="voice-orbit voice-orbit--3" aria-hidden="true">
            <span className="voice-orbit-cross">+</span>
          </span>
          <span className="voice-moon-orbit voice-moon-orbit--1" aria-hidden="true">
            <span className="voice-moon" />
          </span>
          <span className="voice-moon-orbit voice-moon-orbit--2" aria-hidden="true">
            <span className="voice-moon" />
          </span>
          <span className="voice-orb-cross" aria-hidden="true">
            <span className="voice-orb-cross-line voice-orb-cross-line--h" />
            <span className="voice-orb-cross-line voice-orb-cross-line--v" />
          </span>
          <span className="voice-orb-dot" />
        </button>

        {/* State whisper — minimal, below the orb */}
        <div className="voice-fullscreen-label">
          <span className="voice-state-label">{stateLabel}</span>
          <span className="voice-state-sub">{statusSub}</span>
        </div>

        {/* Live caption overlay — last 3 transcript lines, fading upward */}
        {liveCaption.length > 0 && (
          <div className="voice-caption" aria-live="polite">
            {liveCaption.map((item, i) => (
              <div
                key={item.id}
                className={`voice-caption-line voice-caption-line--${item.role}`}
                style={{ opacity: 0.28 + 0.72 * ((i + 1) / liveCaption.length) }}
              >
                <span className="voice-caption-role">{item.role === "hosaka" ? "hosaka" : "you"}</span>
                <span className="voice-caption-text">{item.text}</span>
              </div>
            ))}
          </div>
        )}

        {/* Drawer overlay — slides up over the fullOrb */}
        {drawerOpen && (
          <div className="voice-fullscreen-drawer" role="dialog" aria-label="controls">
            <div className="voice-fullscreen-drawer-actions">
              <button
                className="voice-fullscreen-drawer-shrink"
                onClick={() => { setDrawerOpen(false); setFullOrb(false); }}
                aria-label="shrink orb (exit fullscreen)"
                title="shrink orb"
              >⤢</button>
              <button
                className="voice-fullscreen-drawer-close"
                onClick={() => setDrawerOpen(false)}
                aria-label="close controls"
              >✕</button>
            </div>

            {/* Single ON/OFF — mode is auto-picked (agent if available,
                openai realtime if public build). Power users flip via
                `/voice mode agent|demo` in the cmdline. */}
            <div className="voice-controls-card">
              <div className="voice-controls-row">
                <button
                  className="btn voice-onoff"
                  onClick={toggleVoiceTurn}
                  disabled={mode === "agent" && agentBusy}
                  data-on={(sessionOpen || agentRecording) ? "true" : "false"}
                >
                  {(sessionOpen || agentRecording) ? "OFF" : agentBusy ? "…" : "ON"}
                </button>
              </div>
              <div className="voice-controls-hint">
                {mode === "agent" ? "local agent" : "openai realtime"}
                {" • /voice for options"}
              </div>
              {error && <div className="voice-error">{error}</div>}
            </div>

            {/* Peripheral device picker */}
            <DevicePanel />
          </div>
        )}

        {/* Chevron — opens drawer overlay; minimize sits beside it for a one-tap exit */}
        <div className="voice-fullscreen-corner">
          <button
            className="voice-fullscreen-minimize"
            onClick={() => setFullOrb(false)}
            aria-label="shrink orb (exit fullscreen)"
            title="shrink orb"
          >⤢</button>
          <button
            className="voice-fullscreen-chevron"
            onClick={() => setDrawerOpen((v) => !v)}
            aria-label={drawerOpen ? "close controls" : "open controls"}
          >
            {drawerOpen ? "✕" : "⌄"}
          </button>
        </div>

        <audio ref={audioRef} autoPlay />
      </div>
    );
  }

  return (
    <div className={`voice-wrap voice-wrap--${visualState}`}>
      {/* ── Orb stage — fills the viewport on small screens ── */}
      <div className="voice-orb-stage">
        <button
          ref={setOrbEl}
          className={`voice-orb voice-orb--${visualState}`}
          onClick={toggleVoiceTurn}
          onContextMenu={(e) => e.preventDefault()}
          aria-label={sessionOpen || agentRecording ? "stop voice session" : "start voice session"}
        >
          <span className="voice-orb-ring" />
          <span className="voice-jupiter-ring voice-jupiter-ring--a" aria-hidden="true" />
          <span className="voice-jupiter-ring voice-jupiter-ring--b" aria-hidden="true" />
          <span className="voice-orbit voice-orbit--1" aria-hidden="true">
            <span className="voice-orbit-cross">+</span>
          </span>
          <span className="voice-orbit voice-orbit--2" aria-hidden="true">
            <span className="voice-orbit-cross">+</span>
          </span>
          <span className="voice-orbit voice-orbit--3" aria-hidden="true">
            <span className="voice-orbit-cross">+</span>
          </span>
          <span className="voice-moon-orbit voice-moon-orbit--1" aria-hidden="true">
            <span className="voice-moon" />
          </span>
          <span className="voice-moon-orbit voice-moon-orbit--2" aria-hidden="true">
            <span className="voice-moon" />
          </span>
          <span className="voice-orb-cross" aria-hidden="true">
            <span className="voice-orb-cross-line voice-orb-cross-line--h" />
            <span className="voice-orb-cross-line voice-orb-cross-line--v" />
          </span>
          <span className="voice-orb-dot" />
        </button>

        <div className="voice-state-stack">
          <div className="voice-state-label">{stateLabel}</div>
          <div className="voice-state-sub">{statusSub}</div>
        </div>

        {/* Drawer toggle — the only persistent control in the orb stage */}
        <button
          className="voice-drawer-toggle"
          onClick={() => setDrawerOpen((v) => !v)}
          aria-label={drawerOpen ? "hide controls" : "show controls"}
        >
          {drawerOpen ? "▼ hide" : "▲ controls"}
        </button>
      </div>

      {/* ── Drawer — slides up on small screens, always visible on large ── */}
      <div className={`voice-drawer${drawerOpen ? " voice-drawer--open" : ""}`}>
        {/* Single ON/OFF — mode is auto-picked. Use `/voice mode agent|demo`
            from the cmdline to flip backends; `/voice cam` for the camera. */}
        <div className="voice-controls-card">
          <div className="voice-controls-row">
            <button
              className="btn voice-onoff"
              onClick={toggleVoiceTurn}
              disabled={mode === "agent" && agentBusy}
              data-on={(sessionOpen || agentRecording) ? "true" : "false"}
            >
              {(sessionOpen || agentRecording) ? "OFF" : agentBusy ? "…" : "ON"}
            </button>
          </div>
          <div className="voice-controls-hint">
            {mode === "agent" ? "local agent" : "openai realtime"}
            {" • /voice for options"}
          </div>
          {error && <div className="voice-error">{error}</div>}
        </div>

        {/* Camera (optional) */}
        {cameraExpanded && (
          <div className="voice-camera-panel">
            <div className="voice-camera-panel-head">
              <div>
                <strong>camera</strong>
                <span>keep parked until hosaka needs eyes.</span>
              </div>
              <div className="voice-camera-toolbar">
                <label className="voice-camera-check">
                  <input type="checkbox" checked={camOn} onChange={(e) => setCamOn(e.target.checked)} />
                  enabled
                </label>
                <button className="btn btn-ghost" onClick={() => setCameraExpanded(false)}>hide</button>
              </div>
            </div>
            <div className="voice-camera voice-camera--expanded">
              <video ref={videoRef} className="voice-video" muted playsInline />
              {camState !== "on" && (
                <div className="voice-camera-overlay">
                  {camState === "off" && "camera off"}
                  {camState === "starting" && "warming up…"}
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

        {/* Transcript */}
        <div className="voice-transcript-card">
          <div className="voice-transcript-head">
            <div className="voice-transcript-meta">
              <strong>transcript</strong>
              <span>
                {mode === "agent"
                  ? agentBusy
                      ? agentPhaseLabel
                      : agentRecording
                        ? "recording · press stop to send"
                        : "press start turn · orb is local-only"
                  : sessionOpen
                    ? `${stateLabel} · session open`
                    : "press start realtime · no API while idle"}
              </span>
            </div>
            <div className="voice-transcript-actions">
              {!followTranscript && (
                <button className="btn btn-ghost" onClick={jumpToLatest}>latest</button>
              )}
              <button
                className="btn btn-ghost"
                onClick={() => setTranscript([])}
                disabled={transcript.length === 0}
              >
                clear
              </button>
            </div>
          </div>

          <div
            ref={transcriptRef}
            className="voice-transcript"
            aria-live="polite"
            onScroll={handleTranscriptScroll}
          >
            {transcript.length === 0 && (
              <p className="voice-empty">
                press the orb to talk. it stays local until you ask for the
                cloud. try "what files are in my home dir" or "show disk usage".
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
