import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Disclosure } from "../components/Disclosure";
import { getPreferredCamConstraints, getPreferredMicConstraints } from "./DevicePanel";

type DiagnosticsPanelProps = {
  active?: boolean;
};

type DiagSnapshot = {
  ok?: boolean;
  generated_at?: string;
  hostname?: string;
  mode?: string;
  system?: Record<string, any>;
  network?: Record<string, any>;
  peripherals?: Record<string, any>;
};

type BrowserDevice = {
  deviceId: string;
  kind: MediaDeviceKind;
  label: string;
};

type CamState = "off" | "starting" | "on" | "error";

function useBrowserDevices(active: boolean) {
  const [devices, setDevices] = useState<BrowserDevice[]>([]);
  const [permission, setPermission] = useState<"unknown" | "granted" | "blocked">("unknown");

  const refresh = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const raw = await navigator.mediaDevices.enumerateDevices();
    setDevices(raw.map((device) => ({
      deviceId: device.deviceId,
      kind: device.kind,
      label: device.label || `${device.kind} (${device.deviceId.slice(0, 8)}…)`,
    })));
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
    navigator.mediaDevices.addEventListener?.("devicechange", refresh);
    return () => navigator.mediaDevices.removeEventListener?.("devicechange", refresh);
  }, [active, refresh]);

  return { devices, permission, refresh, requestLabels };
}

function useAudioMeter(active: boolean) {
  const [level, setLevel] = useState(0);
  const [state, setState] = useState<"off" | "starting" | "on" | "error">("off");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) {
      setLevel(0);
      setState("off");
      return;
    }
    let cancelled = false;
    let raf = 0;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    setState("starting");
    setError(null);

    (async () => {
      try {
        const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AudioCtx) throw new Error("AudioContext unavailable");
        stream = await navigator.mediaDevices.getUserMedia({ audio: getPreferredMicConstraints(), video: false });
        if (cancelled) return;
        ctx = new AudioCtx();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        const source = ctx.createMediaStreamSource(stream);
        source.connect(analyser);
        const buf = new Float32Array(analyser.fftSize);
        let smooth = 0;
        setState("on");
        const tick = () => {
          analyser.getFloatTimeDomainData(buf);
          let sum = 0;
          for (const sample of buf) sum += sample * sample;
          const rms = Math.sqrt(sum / buf.length);
          smooth = smooth * 0.82 + Math.min(1, rms * 8) * 0.18;
          setLevel(smooth);
          raf = requestAnimationFrame(tick);
        };
        tick();
      } catch (exc) {
        if (cancelled) return;
        setError(String(exc));
        setState("error");
      }
    })();

    return () => {
      cancelled = true;
      if (raf) cancelAnimationFrame(raf);
      stream?.getTracks().forEach((track) => track.stop());
      void ctx?.close().catch(() => undefined);
    };
  }, [active]);

  return { level, state, error };
}

function useWebcamPreview(active: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<CamState>("off");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) {
      setState("off");
      return;
    }
    let cancelled = false;
    let stream: MediaStream | null = null;
    setState("starting");
    setError(null);
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, ...getPreferredCamConstraints() },
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
          setError(String(exc));
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [active, tick]);

  return { videoRef, state, error, retry: () => setTick((value) => value + 1) };
}

function statusClass(value: unknown): string {
  if (value === true || value === "console" || value === "on") return "ok";
  if (value === false || value === "error") return "bad";
  return "warn";
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="diag-json">{JSON.stringify(value ?? {}, null, 2)}</pre>;
}

function CountBadge({ label, value }: { label: string; value: number }) {
  return <span className="diag-badge"><strong>{value}</strong> {label}</span>;
}

export function DiagnosticsPanel({ active = true }: DiagnosticsPanelProps) {
  const [snapshot, setSnapshot] = useState<DiagSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [audioTest, setAudioTest] = useState(false);
  const [videoTest, setVideoTest] = useState(false);
  const browser = useBrowserDevices(active);
  const meter = useAudioMeter(active && audioTest);
  const camera = useWebcamPreview(active && videoTest);

  const fetchSnapshot = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch("/api/v1/diag/snapshot");
      if (!resp.ok) throw new Error(`diag snapshot ${resp.status}`);
      setSnapshot(await resp.json());
      setError(null);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    void fetchSnapshot();
    const id = window.setInterval(() => void fetchSnapshot(), 8000);
    return () => window.clearInterval(id);
  }, [active, fetchSnapshot]);

  const grouped = useMemo(() => ({
    audio: browser.devices.filter((device) => device.kind === "audioinput" || device.kind === "audiooutput"),
    video: browser.devices.filter((device) => device.kind === "videoinput"),
  }), [browser.devices]);

  const system = snapshot?.system ?? {};
  const network = snapshot?.network ?? {};
  const peripherals = snapshot?.peripherals ?? {};
  const primary = (network.primary ?? {}) as Record<string, any>;
  const diskRoot = (system.disk_root ?? {}) as Record<string, any>;
  const mem = (system.mem ?? {}) as Record<string, any>;

  return (
    <div className="diagnostics-panel">
      <div className="panel-header diagnostics-header">
        <div>
          <h2><span className="panel-glyph">⚇</span> devices</h2>
          <p className="panel-sub">shared diagnostics for app, terminal, and device mode.</p>
        </div>
        <div className="diagnostics-actions">
          <button type="button" className="secondary-btn" onClick={() => void browser.requestLabels()}>
            grant browser devices
          </button>
          <button type="button" className="secondary-btn" onClick={() => void fetchSnapshot()} disabled={loading}>
            {loading ? "scanning…" : "refresh"}
          </button>
          <a className="secondary-btn diagnostics-link" href="/device" target="_blank" rel="noreferrer">/device</a>
        </div>
      </div>

      {error && <div className="diag-error">{error}</div>}

      <section className="diag-overview" aria-label="diagnostics overview">
        <div className="diag-card diag-card--hero">
          <span className={`diag-dot ${statusClass(snapshot?.ok)}`} />
          <div>
            <div className="diag-label">host</div>
            <div className="diag-value">{snapshot?.hostname ?? "unknown"}</div>
            <div className="diag-small">{snapshot?.mode ?? "mode unknown"} · {snapshot?.generated_at ?? "not scanned yet"}</div>
          </div>
        </div>
        <div className="diag-card">
          <div className="diag-label">network</div>
          <div className="diag-value">{primary.ip ?? primary.tailscale_ip ?? "no ip"}</div>
          <div className="diag-small">{primary.iface ?? "iface ?"} · {primary.ssid ?? "no ssid"}</div>
        </div>
        <div className="diag-card">
          <div className="diag-label">memory</div>
          <div className="diag-value">{mem.used_mb ?? "—"} / {mem.total_mb ?? "—"} MB</div>
          <div className="diag-meter"><span style={{ width: `${mem.total_mb ? Math.min(100, (mem.used_mb / mem.total_mb) * 100) : 0}%` }} /></div>
        </div>
        <div className="diag-card">
          <div className="diag-label">disk /</div>
          <div className="diag-value">{diskRoot.used_gb ?? "—"} / {diskRoot.total_gb ?? "—"} GB</div>
          <div className="diag-meter"><span style={{ width: `${diskRoot.used_percent ?? 0}%` }} /></div>
        </div>
      </section>

      <section className="diag-test-grid">
        <div className="diag-test-card">
          <div className="diag-test-title">audio meter</div>
          <div className="diag-meter diag-meter--audio"><span style={{ width: `${Math.round(meter.level * 100)}%` }} /></div>
          <div className="diag-small">{meter.state}{meter.error ? ` · ${meter.error}` : ""}</div>
          <button type="button" className="secondary-btn" onClick={() => setAudioTest((value) => !value)}>
            {audioTest ? "stop mic test" : "start mic test"}
          </button>
        </div>
        <div className="diag-test-card diag-test-card--video">
          <div className="diag-test-title">camera preview</div>
          {videoTest ? <video ref={camera.videoRef} className="diag-video" muted playsInline /> : <div className="diag-video diag-video--blank">camera off</div>}
          <div className="diag-small">{camera.state}{camera.error ? ` · ${camera.error}` : ""}</div>
          <button type="button" className="secondary-btn" onClick={() => setVideoTest((value) => !value)}>
            {videoTest ? "stop video test" : "start video test"}
          </button>
          {camera.state === "error" && <button type="button" className="secondary-btn" onClick={camera.retry}>retry</button>}
        </div>
      </section>

      <section className="diag-badges" aria-label="browser devices">
        <CountBadge label="browser audio devices" value={grouped.audio.length} />
        <CountBadge label="browser cameras" value={grouped.video.length} />
        <span className={`diag-badge diag-badge--${browser.permission}`}>permissions: {browser.permission}</span>
      </section>

      <div className="diag-disclosures">
        <Disclosure label="browser media devices" defaultOpen level={1}>
          <div className="diag-list">
            {browser.devices.length === 0 ? <div className="dim">no browser devices listed yet.</div> : browser.devices.map((device) => (
              <div key={`${device.kind}:${device.deviceId}`} className="diag-list-row">
                <span>{device.kind}</span>
                <strong>{device.label}</strong>
              </div>
            ))}
          </div>
        </Disclosure>

        <Disclosure label="server peripherals" defaultOpen level={1}>
          <JsonBlock value={peripherals} />
        </Disclosure>

        <Disclosure label="network details" level={1}>
          <JsonBlock value={network} />
        </Disclosure>

        <Disclosure label="system details" level={1}>
          <JsonBlock value={system} />
        </Disclosure>
      </div>
    </div>
  );
}
