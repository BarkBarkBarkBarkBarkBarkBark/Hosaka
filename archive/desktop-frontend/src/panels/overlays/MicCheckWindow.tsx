/**
 * MicCheckWindow — /device check mic overlay.
 *
 * Shows browser permission, enumerated audioinput devices with a dropdown,
 * live dB meter (VU segments + peak), getUserMedia errors verbatim, and
 * exposes a "copy diagnostics" button that yields the spec §9 agent JSON
 * payload for the picoclaw agent to pick up.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AudioMeter,
  DeviceList,
  copyDeviceAgentPayloadToClipboard,
  useAudioMeter,
  useBrowserDevices,
} from "../diagPrimitives";

const STORAGE_KEY = "hosaka.device.mic";

function readPref(): string {
  try { return localStorage.getItem(STORAGE_KEY) ?? "default"; } catch { return "default"; }
}

function writePref(value: string): void {
  try { localStorage.setItem(STORAGE_KEY, value); } catch { /* quota */ }
  window.dispatchEvent(new CustomEvent("hosaka:devicechange", {
    detail: { kind: "audioinput", deviceId: value },
  }));
}

export function MicCheckWindow({ onClose: _onClose }: { onClose: () => void }) {
  const [running, setRunning] = useState(true);
  const [deviceId, setDeviceId] = useState<string>(readPref());
  const browser = useBrowserDevices(true);
  const { sample } = useAudioMeter(running, deviceId);
  const [copyTip, setCopyTip] = useState<string>("");

  useEffect(() => {
    if (browser.permission === "unknown" && sample.state === "on") {
      // we got mic access already; surface that to the UI
    }
  }, [browser.permission, sample.state]);

  const levelDb = useMemo(() => {
    if (sample.rms <= 0) return -Infinity;
    return 20 * Math.log10(sample.rms);
  }, [sample.rms]);

  const onSelect = useCallback((nextId: string) => {
    setDeviceId(nextId);
    writePref(nextId);
  }, []);

  const onCopy = useCallback(async () => {
    const ok = await copyDeviceAgentPayloadToClipboard("mic", {
      permission: browser.permission,
      devices: browser.devices,
      gumError: sample.error ? { name: "getUserMedia", message: sample.error } : null,
      level: sample.level,
    });
    setCopyTip(ok ? "copied agent payload" : "copy failed");
    window.setTimeout(() => setCopyTip(""), 2000);
  }, [browser.permission, browser.devices, sample.error, sample.level]);

  const stateDot = sample.state === "on"
    ? "is-ok"
    : sample.state === "error"
      ? "is-err"
      : sample.state === "starting" ? "is-warn" : "";

  return (
    <div className="instrument">
      <div className="instrument-row">
        <span className={`instrument-dot ${stateDot}`} aria-hidden />
        <span className="instrument-label">state</span>
        <span className="instrument-value">{sample.state}</span>
        <span className="instrument-label" style={{ marginLeft: 10 }}>perm</span>
        <span className="instrument-value">{browser.permission}</span>
      </div>

      <AudioMeter level={sample.level} peak={sample.peak} />
      <div className="instrument-row">
        <span className="instrument-label">rms</span>
        <span className="instrument-value">{sample.rms.toFixed(4)}</span>
        <span className="instrument-label">dbfs</span>
        <span className="instrument-value">{Number.isFinite(levelDb) ? levelDb.toFixed(1) : "-∞"} dB</span>
      </div>

      <DeviceList
        devices={browser.devices}
        kind="audioinput"
        value={deviceId}
        onChange={onSelect}
        label="device"
      />

      {sample.error && (
        <div className="instrument-note instrument-note--err">{sample.error}</div>
      )}
      {browser.permission !== "granted" && (
        <div className="instrument-note">
          some device names are hidden until browser permission is granted.
        </div>
      )}

      <div className="instrument-actions">
        <button
          type="button"
          className={`instrument-btn ${running ? "is-on" : ""}`}
          onClick={() => setRunning((v) => !v)}
        >{running ? "stop meter" : "start meter"}</button>
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
    </div>
  );
}
