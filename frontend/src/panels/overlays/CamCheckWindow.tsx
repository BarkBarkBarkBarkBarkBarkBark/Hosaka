/**
 * CamCheckWindow — /device check cam overlay.
 *
 * Compressed video thumbnail (~480×270 @ ~15fps), camera picker, permission
 * + error surface, and a "copy diagnostics" button for the agent.
 */
import { useCallback, useState } from "react";
import {
  DeviceList,
  copyDeviceAgentPayloadToClipboard,
  useBrowserDevices,
  useWebcamPreview,
} from "../diagPrimitives";

const STORAGE_KEY = "hosaka.device.cam";

function readPref(): string {
  try { return localStorage.getItem(STORAGE_KEY) ?? "default"; } catch { return "default"; }
}
function writePref(value: string): void {
  try { localStorage.setItem(STORAGE_KEY, value); } catch { /* quota */ }
  window.dispatchEvent(new CustomEvent("hosaka:devicechange", {
    detail: { kind: "videoinput", deviceId: value },
  }));
}

export function CamCheckWindow({ onClose: _onClose }: { onClose: () => void }) {
  const [running, setRunning] = useState(true);
  const [deviceId, setDeviceId] = useState<string>(readPref());
  const browser = useBrowserDevices(true);
  const camera = useWebcamPreview(running, deviceId);
  const [copyTip, setCopyTip] = useState<string>("");

  const onSelect = useCallback((nextId: string) => {
    setDeviceId(nextId);
    writePref(nextId);
  }, []);

  const onCopy = useCallback(async () => {
    const ok = await copyDeviceAgentPayloadToClipboard("cam", {
      permission: browser.permission,
      devices: browser.devices,
      gumError: camera.error ? { name: "getUserMedia", message: camera.error } : null,
    });
    setCopyTip(ok ? "copied agent payload" : "copy failed");
    window.setTimeout(() => setCopyTip(""), 2000);
  }, [browser.permission, browser.devices, camera.error]);

  const stateDot = camera.state === "on"
    ? "is-ok"
    : camera.state === "error"
      ? "is-err"
      : camera.state === "starting" ? "is-warn" : "";

  return (
    <div className="instrument">
      <div className="instrument-row">
        <span className={`instrument-dot ${stateDot}`} aria-hidden />
        <span className="instrument-label">state</span>
        <span className="instrument-value">{camera.state}</span>
        <span className="instrument-label" style={{ marginLeft: 10 }}>perm</span>
        <span className="instrument-value">{browser.permission}</span>
      </div>

      {running
        ? <video ref={camera.videoRef} className="instrument-video" muted playsInline />
        : <div className="instrument-video instrument-video--blank">camera off</div>
      }

      <DeviceList
        devices={browser.devices}
        kind="videoinput"
        value={deviceId}
        onChange={onSelect}
        label="device"
      />

      {camera.error && (
        <div className="instrument-note instrument-note--err">
          {/^camera blocked:.*secure/i.test(camera.error) || /api unavailable/i.test(camera.error) ? (
            <>
              <strong>⚠ secure context required</strong><br />
              browsers block camera/mic on plain HTTP outside localhost.<br />
              access hosaka via <code>http://localhost</code> or enable HTTPS on the host.
            </>
          ) : camera.error}
        </div>
      )}

      <div className="instrument-actions">
        <button
          type="button"
          className={`instrument-btn ${running ? "is-on" : ""}`}
          onClick={() => setRunning((v) => !v)}
        >{running ? "stop preview" : "start preview"}</button>
        {camera.state === "error" && (
          <button type="button" className="instrument-btn" onClick={camera.retry}>retry</button>
        )}
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
