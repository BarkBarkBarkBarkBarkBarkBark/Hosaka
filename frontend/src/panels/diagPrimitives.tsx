/**
 * diagPrimitives — shared hooks/components for the diagnostics panel and
 * the floating instrument overlays (/device check mic|cam|spk).
 *
 * Keeps getUserMedia lifecycles in exactly one place so mic/cam stop
 * cleanly when any consumer unmounts. No duplication between
 * DiagnosticsPanel, DeviceCheckWindow*, or VoicePanel beyond small
 * constraint helpers from DevicePanel.tsx.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getPreferredCamConstraints, getPreferredMicConstraints } from "./DevicePanel";

export type BrowserDevice = {
  deviceId: string;
  groupId: string;
  kind: MediaDeviceKind;
  label: string;
};

export type PermissionState = "unknown" | "granted" | "blocked";
export type MeterState = "off" | "starting" | "on" | "error";

/* ── useBrowserDevices ──────────────────────────────────────────────────── */

export function useBrowserDevices(active: boolean) {
  const [devices, setDevices] = useState<BrowserDevice[]>([]);
  const [permission, setPermission] = useState<PermissionState>("unknown");

  const refresh = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const raw = await navigator.mediaDevices.enumerateDevices();
      setDevices(raw.map((device) => ({
        deviceId: device.deviceId,
        groupId: device.groupId,
        kind: device.kind,
        label: device.label || `${device.kind} (${device.deviceId.slice(0, 8)}…)`,
      })));
    } catch {
      // Device enumeration can throw in privacy modes; leave prior list.
    }
  }, []);

  const requestLabels = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      stream.getTracks().forEach((track) => track.stop());
      setPermission("granted");
    } catch {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((track) => track.stop());
        setPermission("granted");
      } catch {
        setPermission("blocked");
      }
    }
    await refresh();
  }, [refresh]);

  useEffect(() => {
    if (!active || !navigator.mediaDevices) return;
    void refresh();
    const handler = () => void refresh();
    navigator.mediaDevices.addEventListener?.("devicechange", handler);
    return () => navigator.mediaDevices.removeEventListener?.("devicechange", handler);
  }, [active, refresh]);

  return { devices, permission, refresh, requestLabels };
}

/* ── friendly media error mapper ─────────────────────────────────────────
 * getUserMedia errors are not super readable. Map the common DOMException
 * names to short human strings tailored to the device kind. */
export function friendlyMediaError(exc: unknown, kind: "mic" | "cam"): string {
  const dev = kind === "mic" ? "microphone" : "camera";
  const e = exc as { name?: string; message?: string } | null | undefined;
  const name = e?.name ?? "";
  const msg = e?.message ?? String(exc);
  switch (name) {
    case "NotReadableError":
      return `${dev} busy: another app (zoom, browser tab, voice agent) is holding it. close that and retry.`;
    case "NotAllowedError":
      return `${dev} blocked: browser permission denied. open site settings → allow ${dev} → retry.`;
    case "NotFoundError":
    case "OverconstrainedError":
      return `no ${dev} matched the requested device. unplug/replug, or pick a different device.`;
    case "AbortError":
      return `${dev} aborted: hardware glitch or session interrupted. retry usually works.`;
    case "SecurityError":
      return `${dev} blocked: page is not a secure origin. use https:// or localhost.`;
    case "TypeError":
      return `${dev} api unavailable in this browser context (likely insecure http on a non-localhost ip).`;
    default:
      return `${dev} error: ${name || "unknown"} — ${msg}`;
  }
}

/* ── useAudioMeter ──────────────────────────────────────────────────────── */

export type AudioMeterSample = {
  level: number;
  rms: number;
  peak: number;
  state: MeterState;
  error: string | null;
};

/**
 * Returns a smoothed VU-style level (0..1), the raw RMS, and a rolling peak
 * estimator, plus a liveSample ref for read-on-demand use in agent payloads.
 *
 * When active is false, the stream/AudioContext are torn down so nothing
 * holds the mic warm.
 */
export function useAudioMeter(active: boolean, deviceIdOverride?: string) {
  const [sample, setSample] = useState<AudioMeterSample>({
    level: 0, rms: 0, peak: 0, state: "off", error: null,
  });
  const liveRef = useRef<AudioMeterSample>(sample);
  liveRef.current = sample;

  useEffect(() => {
    if (!active) {
      setSample({ level: 0, rms: 0, peak: 0, state: "off", error: null });
      return;
    }
    let cancelled = false;
    let raf = 0;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    setSample((prev) => ({ ...prev, state: "starting", error: null }));

    if (!navigator.mediaDevices?.getUserMedia) {
      const isInsecure = location.protocol !== "https:" && location.hostname !== "localhost";
      setSample((prev) => ({
        ...prev,
        state: "error",
        error: isInsecure
          ? "Mic blocked: browser requires HTTPS (or localhost) for media access."
          : "navigator.mediaDevices unavailable.",
      }));
      return;
    }
    (async () => {
      try {
        const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AudioCtx) throw new Error("AudioContext unavailable");
        const base = getPreferredMicConstraints();
        const audio: MediaTrackConstraints = deviceIdOverride && deviceIdOverride !== "default"
          ? { ...base, deviceId: { exact: deviceIdOverride } }
          : base;
        stream = await navigator.mediaDevices.getUserMedia({ audio, video: false });
        if (cancelled) return;
        ctx = new AudioCtx();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        const source = ctx.createMediaStreamSource(stream);
        source.connect(analyser);
        const buf = new Float32Array(analyser.fftSize);
        let smooth = 0;
        let peak = 0;
        let peakDecay = 0;
        const tick = () => {
          analyser.getFloatTimeDomainData(buf);
          let sum = 0;
          for (const sampleVal of buf) sum += sampleVal * sampleVal;
          const rms = Math.sqrt(sum / buf.length);
          smooth = smooth * 0.82 + Math.min(1, rms * 8) * 0.18;
          if (smooth > peak) {
            peak = smooth;
            peakDecay = 0;
          } else if (++peakDecay > 24) {
            peak = peak * 0.94;
          }
          setSample({ level: smooth, rms, peak, state: "on", error: null });
          raf = requestAnimationFrame(tick);
        };
        tick();
      } catch (exc) {
        if (cancelled) return;
        setSample({ level: 0, rms: 0, peak: 0, state: "error", error: friendlyMediaError(exc, "mic") });
      }
    })();

    return () => {
      cancelled = true;
      if (raf) cancelAnimationFrame(raf);
      stream?.getTracks().forEach((track) => track.stop());
      void ctx?.close().catch(() => undefined);
    };
  }, [active, deviceIdOverride]);

  return { sample, liveRef };
}

/* ── useWebcamPreview ───────────────────────────────────────────────────── */

export type CamState = "off" | "starting" | "on" | "error";

export function useWebcamPreview(active: boolean, deviceIdOverride?: string) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<CamState>("off");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) {
      setState("off");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      const isInsecure = location.protocol !== "https:" && location.hostname !== "localhost";
      setError(
        isInsecure
          ? "Camera blocked: browser requires HTTPS (or localhost) for media access. " +
            "On the Pi, enable HTTPS or access via localhost."
          : "navigator.mediaDevices unavailable in this browser context."
      );
      setState("error");
      return;
    }
    let cancelled = false;
    let stream: MediaStream | null = null;
    setState("starting");
    setError(null);
    (async () => {
      try {
        const base = getPreferredCamConstraints();
        const video: MediaTrackConstraints = deviceIdOverride && deviceIdOverride !== "default"
          ? { ...base, deviceId: { exact: deviceIdOverride } }
          : base;
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 480 }, height: { ideal: 270 }, frameRate: { ideal: 15 }, ...video },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
        setState("on");
      } catch (exc) {
        if (!cancelled) {
          setError(friendlyMediaError(exc, "cam"));
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [active, deviceIdOverride, tick]);

  const retry = useCallback(() => setTick((value) => value + 1), []);
  return { videoRef, state, error, retry };
}

/* ── small primitives ──────────────────────────────────────────────────── */

export function AudioMeter({ level, peak, segments = 20 }: { level: number; peak?: number; segments?: number }) {
  const segs = useMemo(() => {
    const lit = Math.round(level * segments);
    const peakSeg = peak ? Math.min(segments - 1, Math.round(peak * segments)) : -1;
    return Array.from({ length: segments }, (_, i) => {
      const on = i < lit || i === peakSeg;
      const cls = on ? (i >= segments - 3 ? "is-on is-hot" : i >= segments - 6 ? "is-on is-warn" : "is-on") : "";
      return <span key={i} className={`seg ${cls}`} />;
    });
  }, [level, peak, segments]);
  return <div className="instrument-meter instrument-meter--segments" aria-label="audio level">{segs}</div>;
}

type DeviceListProps = {
  devices: BrowserDevice[];
  kind: MediaDeviceKind;
  value: string;
  onChange: (deviceId: string) => void;
  label?: string;
  includeSystemDefault?: boolean;
};

export function DeviceList({
  devices, kind, value, onChange, label, includeSystemDefault = true,
}: DeviceListProps) {
  const filtered = useMemo(
    () => devices.filter((device) => device.kind === kind && device.deviceId && device.deviceId !== "communications"),
    [devices, kind],
  );
  return (
    <label className="instrument-row">
      {label && <span className="instrument-label">{label}</span>}
      <select
        className="instrument-select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {includeSystemDefault && <option value="default">system default</option>}
        {filtered.map((device) => (
          <option key={device.deviceId} value={device.deviceId}>
            {device.label}
          </option>
        ))}
        {filtered.length === 0 && !includeSystemDefault && (
          <option value="" disabled>no {kind} devices</option>
        )}
      </select>
    </label>
  );
}

export function DiagnosticJsonBlock({ value }: { value: unknown }) {
  return <pre className="diag-json">{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

/* ── agent-friendly payload ─────────────────────────────────────────────── */

export type DeviceCheckKind = "mic" | "cam" | "spk";

export type DeviceAgentPayload = {
  kind: DeviceCheckKind;
  generatedAt: string;
  permission: PermissionState;
  browserDevices: BrowserDevice[];
  selectedDeviceIds: {
    mic: string;
    cam: string;
    spk: string;
  };
  getUserMedia: {
    ok: boolean;
    errorName?: string;
    errorMessage?: string;
  } | null;
  liveLevel: number | null;
  peripherals: Record<string, unknown> | null;
  toolAvailability: Record<string, boolean>;
  rawSnapshotMode: string | null;
};

function readPref(key: string): string {
  try { return localStorage.getItem(key) ?? "default"; } catch { return "default"; }
}

export async function fetchDiagSnapshot(): Promise<Record<string, any> | null> {
  try {
    const resp = await fetch("/api/v1/diag/snapshot");
    if (!resp.ok) return null;
    return await resp.json() as Record<string, any>;
  } catch {
    return null;
  }
}

export async function buildDeviceAgentPayload(
  kind: DeviceCheckKind,
  state: {
    permission: PermissionState;
    devices: BrowserDevice[];
    gumError?: { name?: string; message?: string } | null;
    level?: number | null;
  },
): Promise<DeviceAgentPayload> {
  const snapshot = await fetchDiagSnapshot();
  const peripherals = (snapshot?.peripherals ?? null) as Record<string, unknown> | null;
  const per = (peripherals ?? {}) as Record<string, any>;
  const tools: Record<string, boolean> = {
    pactl: Boolean(per.audio?.pactl?.available),
    arecord: Boolean(per.audio?.arecord?.available),
    aplay: Boolean(per.audio?.aplay?.available),
    "v4l2-ctl": Boolean(per.video?.v4l2?.available),
    bluetoothctl: Boolean(per.bluetooth?.bluetoothctl?.available),
  };
  const gumOk = state.gumError == null;
  return {
    kind,
    generatedAt: new Date().toISOString(),
    permission: state.permission,
    browserDevices: state.devices,
    selectedDeviceIds: {
      mic: readPref("hosaka.device.mic"),
      cam: readPref("hosaka.device.cam"),
      spk: readPref("hosaka.device.spk"),
    },
    getUserMedia: state.gumError !== undefined
      ? { ok: gumOk, errorName: state.gumError?.name, errorMessage: state.gumError?.message }
      : null,
    liveLevel: state.level ?? null,
    peripherals,
    toolAvailability: tools,
    rawSnapshotMode: (snapshot?.mode as string | undefined) ?? null,
  };
}

export async function copyDeviceAgentPayloadToClipboard(
  kind: DeviceCheckKind,
  state: Parameters<typeof buildDeviceAgentPayload>[1],
): Promise<boolean> {
  const payload = await buildDeviceAgentPayload(kind, state);
  const text = JSON.stringify(payload, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function statusClass(value: unknown): "ok" | "bad" | "warn" {
  if (value === true || value === "console" || value === "on") return "ok";
  if (value === false || value === "error") return "bad";
  return "warn";
}
