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
  role: "you" | "hosaka" | "tool" | "status";
  text: string;
};

type VoiceMode = "agent" | "demo";

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
 * Returns a normalised 0–1 value (0 = silence / –60 dB, 1 = peak / 0 dB).
 * Attaches a CSS custom-property writer to an optional orb element:
 *   --v-scale   ring radius multiplier  (1.0 – 1.55)
 *   --v-glow    extra glow strength     (0.0 – 1.0)
 *   --v-speed   animation speed factor  (1.0 – 2.0)
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

  useEffect(() => {
    if (!stream) {
      // fade out smoothly when stream disappears
      const fade = () => {
        smoothRef.current *= 0.85;
        const v = smoothRef.current;
        if (orbEl) {
          orbEl.style.setProperty("--v-scale", String(1 + v * 0.55));
          orbEl.style.setProperty("--v-glow", String(v));
          orbEl.style.setProperty("--v-speed", String(1 + v));
        }
        setLevel(v);
        if (v > 0.001 && rafRef.current !== null) {
          rafRef.current = requestAnimationFrame(fade);
        } else {
          rafRef.current = null;
        }
      };
      if (rafRef.current === null) rafRef.current = requestAnimationFrame(fade);
      return;
    }

    let cancelled = false;
    const AudioCtx = window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx = new AudioCtx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0; // we do our own EMA
    const buf = new Float32Array(analyser.fftSize);
    bufRef.current = buf;
    ctxRef.current = ctx;
    nodeRef.current = analyser;

    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);

    // EMA alpha ≈ 1 – e^(–1/(fps*tau)) with tau≈0.08s → alpha≈0.13 at 60fps
    const ALPHA = 0.13;
    const DB_FLOOR = -60;
    const DB_CEIL = -10;

    const tick = () => {
      if (cancelled) return;
      analyser.getFloatTimeDomainData(buf);
      let sq = 0;
      for (let i = 0; i < buf.length; i++) sq += buf[i] * buf[i];
      const rms = Math.sqrt(sq / buf.length);
      const db = rms < 1e-9 ? DB_FLOOR : 20 * Math.log10(rms);
      const raw = Math.max(0, Math.min(1, (db - DB_FLOOR) / (DB_CEIL - DB_FLOOR)));
      smoothRef.current = ALPHA * raw + (1 - ALPHA) * smoothRef.current;
      const v = smoothRef.current;
      if (orbEl) {
        orbEl.style.setProperty("--v-scale", String(1 + v * 0.55));
        orbEl.style.setProperty("--v-glow", String(v));
        orbEl.style.setProperty("--v-speed", String(1 + v));
      }
      setLevel(v);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
      try { source.disconnect(); } catch {/* noop */}
      ctx.close().catch(() => undefined);
      ctxRef.current = null;
      nodeRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream, orbEl]);

  return level;
}

/** Keeps a mic stream open as long as the panel is active + not muted. */
function usePersistentMic(active: boolean, muted: boolean): MediaStream | null {
  const [stream, setStream] = useState<MediaStream | null>(null);
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
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
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
  }, [active, muted]);
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

    const SPEECH_THRESHOLD = 0.08;   // RMS above → speech
    const SILENCE_THRESHOLD = 0.035; // RMS below → silence
    const SPEECH_ONSET_MS = 160;     // must sustain before firing onSpeechStart
    const SILENCE_END_MS  = 1400;    // must sustain before firing onSpeechEnd
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
  const [publicMode, setPublicMode] = useState(false);
  // Orb-first mode: orb fills the screen, drawer slides up for transcript + controls.
  // Default to orb-first on narrow viewports.
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Full-screen orb mode: the orb is the entire panel — one chevron exits.
  const [fullOrb, setFullOrb] = useState(true);
  const sessionRef = useRef<VoiceSession | null>(null);
  const agentRecorderRef = useRef<MediaRecorder | null>(null);
  const agentStreamRef = useRef<MediaStream | null>(null);
  const agentChunksRef = useRef<Blob[]>([]);
  const agentRunNonceRef = useRef(0);
  const speakingResetRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const orbRef = useRef<HTMLButtonElement>(null);
  const [muted, setMuted] = useState(false);
  // Live caption: last 2 visible transcript items for orb overlay
  const [liveCaption, setLiveCaption] = useState<TranscriptItem[]>([]);

  // Always-on mic stream — open whenever panel is active in agent mode and not muted.
  const micStream = usePersistentMic(active && mode === "agent", muted);
  // Ref so closures (VAD callbacks, startAgentRecording) always see the latest stream.
  const micStreamRef = useRef<MediaStream | null>(null);
  micStreamRef.current = micStream;

  // Feed the persistent stream to the orb visualiser (always-on mic reactivity).
  useVoiceAnalyser(micStream, orbRef.current);

  const { videoRef, state: camState, error: camError, retry: retryCam } =
    useWebcamPreview(active && camOn && cameraExpanded);

  const appendTranscript = (role: TranscriptItem["role"], text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setTranscript((t) => [
      ...t.slice(-(maxTranscriptItems - 1)),
      { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, role, text: trimmed },
    ]);
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
    if (mode !== "agent") {
      agentRunNonceRef.current += 1;
      setAgentBusy(false);
      setAgentPhase("idle");
    }
  }, [mode]);

  // VAD: auto-start recording on speech, auto-stop on silence.
  // Disabled while agent is busy (processing previous turn) or in demo mode.
  useVAD(
    micStream,
    () => { void startAgentRecording(); },
    () => { void stopAgentRecording(); },
    mode === "agent" && !muted && !agentBusy,
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
      case "recording": return "hold to speak · release to send";
      case "uploading": return "packaging the turn";
      case "transcribing": return "whisper is transcribing";
      case "thinking": return "picoclaw is working";
      default: return "backend-first local agent";
    }
  }, [agentPhase]);

  const statusSub = mode === "agent"
    ? muted
      ? "tap to unmute"
      : agentRecording
        ? "listening · will send on silence"
        : agentBusy
          ? agentPhaseLabel
          : micStream
            ? "always listening · speak naturally"
            : "opening mic…"
    : sessionOpen
      ? "mic open · realtime link live"
      : "ready when you are";

  if (fullOrb) {
    return (
      <div className={`voice-fullscreen voice-fullscreen--${visualState}`}>
        {/* Full-screen ambient haze */}
        <div className="voice-fullscreen-haze" aria-hidden="true" />

        {/* The orb — fills most of the screen */}
        <button
          ref={orbRef}
          className={`voice-orb voice-orb--full voice-orb--${visualState}`}
          onClick={mode === "demo"
            ? () => (sessionOpen ? stopSession() : startSession())
            : () => setMuted((v) => !v)}
          onPointerDown={mode === "agent" ? (e) => e.currentTarget.setPointerCapture(e.pointerId) : undefined}
          onContextMenu={(e) => e.preventDefault()}
          aria-label={mode === "agent" ? (muted ? "unmute" : "mute") : (sessionOpen ? "end" : "start")}
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
          {muted && <span className="voice-state-sub">tap orb to unmute</span>}
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

        {/* Chevron — the only exit */}
        <button
          className="voice-fullscreen-chevron"
          onClick={() => setFullOrb(false)}
          aria-label="open controls"
        >
          ⌄
        </button>

        <audio ref={audioRef} autoPlay />
      </div>
    );
  }

  return (
    <div className={`voice-wrap voice-wrap--${visualState}`}>
      {/* ── Orb stage — fills the viewport on small screens ── */}
      <div className="voice-orb-stage">
        <button
          ref={orbRef}
          className={`voice-orb voice-orb--${visualState}`}
          onClick={mode === "demo" ? () => (sessionOpen ? stopSession() : startSession()) : mode === "agent" ? () => setMuted((v) => !v) : undefined}
          onPointerDown={mode === "agent" ? (e) => { e.currentTarget.setPointerCapture(e.pointerId); } : undefined}
          onContextMenu={mode === "agent" ? (e) => e.preventDefault() : undefined}
          aria-label={mode === "agent"
            ? (muted ? "unmute hosaka" : "mute hosaka")
            : (sessionOpen ? "end voice session" : "start voice session")}
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

        {/* Mute toggle — always visible in agent mode */}
        {mode === "agent" && (
          <button
            className={`voice-mute-btn${muted ? " voice-mute-btn--muted" : ""}`}
            onClick={() => setMuted((v) => !v)}
            aria-pressed={muted}
            aria-label={muted ? "unmute" : "mute"}
          >
            {muted ? "● unmute" : "○ mute"}
          </button>
        )}

        {/* Drawer toggle — visible on small screens */}
        <button
          className="voice-drawer-toggle"
          onClick={() => setDrawerOpen((v) => !v)}
          aria-label={drawerOpen ? "hide transcript" : "show transcript"}
        >
          {drawerOpen ? "▼ hide" : "▲ transcript"}
        </button>

        {/* Expand to full orb */}
        <button
          className="voice-expand-btn"
          onClick={() => setFullOrb(true)}
          aria-label="full screen orb"
        >
          ⌃ all orb
        </button>
      </div>

      {/* ── Drawer — slides up on small screens, always visible on large ── */}
      <div className={`voice-drawer${drawerOpen ? " voice-drawer--open" : ""}`}>
        {/* Controls strip */}
        <div className="voice-controls-card">
          {!publicMode && (
            <div className="voice-mode-switch" role="tablist" aria-label="voice mode">
              <button
                className={`pill ${mode === "agent" ? "is-active" : ""}`}
                onClick={() => setMode("agent")}
                aria-pressed={mode === "agent"}
              >
                local agent
              </button>
              <button
                className={`pill ${mode === "demo" ? "is-active" : ""}`}
                onClick={() => setMode("demo")}
                aria-pressed={mode === "demo"}
              >
                openai realtime
              </button>
            </div>
          )}

          {publicMode && (
            <div className="voice-build-note">
              public build: realtime demo only
            </div>
          )}

          <div className="voice-controls-row">
            <button
              className="btn"
              onClick={mode === "demo" ? toggleVoiceTurn : () => setMuted((v) => !v)}
              disabled={mode === "agent" && agentBusy}
            >
              {mode === "agent"
                ? muted
                  ? "unmute"
                  : agentRecording
                    ? "listening…"
                    : agentBusy
                      ? "working…"
                      : "mute"
                : sessionOpen
                  ? "end session"
                  : "start listening"}
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => setCameraExpanded((v) => !v)}
            >
              {cameraExpanded ? "hide cam" : "camera"}
            </button>
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
                  ? muted
                    ? "muted · tap orb to unmute"
                    : agentBusy
                      ? agentPhaseLabel
                      : agentRecording
                        ? "listening · will send on silence"
                        : "always listening · just speak"
                  : sessionOpen
                    ? `${stateLabel} · session open`
                    : "tap start listening"}
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
                {mode === "agent"
                  ? "just speak — hosaka is listening. try 'what files are in my home dir' or 'show disk usage'."
                  : "say 'how are you', 'what do you see', or 'add a todo: buy coffee'."}
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
