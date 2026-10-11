/**
 * SpkCheckWindow — /device check spk overlay.
 *
 * Lists audiooutput devices (when Chromium supports enumerateDevices +
 * setSinkId), lets the operator pick one, plays a short 440 Hz test tone
 * through the selected sink so they can confirm the physical path.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  DeviceList,
  copyDeviceAgentPayloadToClipboard,
  useBrowserDevices,
} from "../diagPrimitives";

const STORAGE_KEY = "hosaka.device.spk";

function readPref(): string {
  try { return localStorage.getItem(STORAGE_KEY) ?? "default"; } catch { return "default"; }
}
function writePref(value: string): void {
  try { localStorage.setItem(STORAGE_KEY, value); } catch { /* quota */ }
  window.dispatchEvent(new CustomEvent("hosaka:devicechange", {
    detail: { kind: "audiooutput", deviceId: value },
  }));
}

type HTMLAudioWithSink = HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> };

async function applySinkToElement(el: HTMLAudioWithSink, deviceId: string): Promise<void> {
  if (!deviceId || deviceId === "default") return;
  if (typeof el.setSinkId !== "function") return;
  try { await el.setSinkId(deviceId); } catch { /* ignore */ }
}

export function SpkCheckWindow({ onClose: _onClose }: { onClose: () => void }) {
  const browser = useBrowserDevices(true);
  const [deviceId, setDeviceId] = useState<string>(readPref());
  const [playing, setPlaying] = useState(false);
  const [tip, setTip] = useState<string>("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const [copyTip, setCopyTip] = useState<string>("");

  useEffect(() => {
    return () => {
      try { ctxRef.current?.close(); } catch { /* noop */ }
      ctxRef.current = null;
    };
  }, []);

  const supportsSinkId = useRef<boolean | null>(null);
  useEffect(() => {
    const probe = document.createElement("audio") as HTMLAudioWithSink;
    supportsSinkId.current = typeof probe.setSinkId === "function";
  }, []);

  const onSelect = useCallback(async (next: string) => {
    setDeviceId(next);
    writePref(next);
    if (audioRef.current) await applySinkToElement(audioRef.current as HTMLAudioWithSink, next);
  }, []);

  const playTone = useCallback(async () => {
    if (playing) return;
    setPlaying(true);
    setTip("");
    try {
      const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) throw new Error("AudioContext unavailable");
      const ctx = new AudioCtx();
      ctxRef.current = ctx;
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = 440;
      const gain = ctx.createGain();
      gain.gain.value = 0.0001;
      const dest = ctx.createMediaStreamDestination();
      osc.connect(gain);
      gain.connect(dest);
      // Route the oscillator through a hidden <audio> so setSinkId applies.
      const audio = (audioRef.current ?? document.createElement("audio")) as HTMLAudioWithSink;
      audio.autoplay = true;
      audio.srcObject = dest.stream;
      audioRef.current = audio;
      await applySinkToElement(audio, deviceId);
      await audio.play().catch(() => undefined);
      osc.start();
      const t = ctx.currentTime;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.18, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.42);
      osc.stop(t + 0.45);
      window.setTimeout(async () => {
        try { audio.srcObject = null; } catch { /* noop */ }
        try { await ctx.close(); } catch { /* noop */ }
        if (ctxRef.current === ctx) ctxRef.current = null;
        setPlaying(false);
      }, 550);
    } catch (exc) {
      setTip(String(exc));
      setPlaying(false);
    }
  }, [deviceId, playing]);

  const onCopy = useCallback(async () => {
    const ok = await copyDeviceAgentPayloadToClipboard("spk", {
      permission: browser.permission,
      devices: browser.devices,
    });
    setCopyTip(ok ? "copied agent payload" : "copy failed");
    window.setTimeout(() => setCopyTip(""), 2000);
  }, [browser.permission, browser.devices]);

  return (
    <div className="instrument">
      <div className="instrument-row">
        <span className="instrument-label">sink api</span>
        <span className="instrument-value">
          {supportsSinkId.current === false ? "unsupported (tone plays on system default)" : "setSinkId ready"}
        </span>
      </div>

      <DeviceList
        devices={browser.devices}
        kind="audiooutput"
        value={deviceId}
        onChange={(id) => void onSelect(id)}
        label="device"
      />

      {tip && <div className="instrument-note instrument-note--err">{tip}</div>}

      <div className="instrument-actions">
        <button
          type="button"
          className={`instrument-btn ${playing ? "is-on" : ""}`}
          disabled={playing}
          onClick={() => void playTone()}
        >{playing ? "playing…" : "test tone"}</button>
        <button
          type="button"
          className="instrument-btn"
          onClick={() => void browser.requestLabels()}
        >grant permission</button>
        <button
          type="button"
          className="instrument-btn"
          onClick={() => void browser.refresh()}
        >refresh devices</button>
        <button
          type="button"
          className="instrument-btn"
          onClick={() => void onCopy()}
        >copy diagnostics</button>
        {copyTip && <span className="instrument-note">{copyTip}</span>}
      </div>

      <audio
        ref={(el) => { audioRef.current = el; }}
        style={{ display: "none" }}
        autoPlay
        playsInline
      />
    </div>
  );
}
