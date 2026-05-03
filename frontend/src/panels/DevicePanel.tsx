// DevicePanel — peripheral device picker for mic, camera, and speaker.
//
// Uses navigator.mediaDevices.enumerateDevices() to list available devices.
// Each category has a toggle-to-expand dropdown. Selecting a device stores
// its deviceId in localStorage so VoicePanel can pick it up on next open.
//
// Speaker (audio output) selection uses HTMLMediaElement.setSinkId(), which
// is supported in Chromium-based browsers (Electron on Pi ✓).

import { useEffect, useState } from "react";

type Device = {
  deviceId: string;
  label: string;
  kind: MediaDeviceKind;
};

type Category = {
  kind: MediaDeviceKind;
  icon: string;
  label: string;
  storageKey: string;
};

const CATEGORIES: Category[] = [
  { kind: "audioinput",  icon: "🎙",  label: "microphone",  storageKey: "hosaka.device.mic" },
  { kind: "videoinput",  icon: "📷",  label: "camera",      storageKey: "hosaka.device.cam" },
  { kind: "audiooutput", icon: "🔊",  label: "speaker",     storageKey: "hosaka.device.spk" },
];

// ALSA / Pulse aliases that show up in Chromium's enumerateDevices() but
// are not user-meaningful: monitor loopbacks, ALSA "front:" / "surround:" /
// "iec958:" / "snoop:" virtuals, etc. We keep the friendly card label per
// physical device (groupId) and drop these clones.
const NOISE_LABEL_RE = /\b(monitor of|loopback|sample snooping|direct (sample )?(snooping|hardware)|front:|surround(2[01]|40|41|50|51|71)|iec958:|spdif|hdmi:CARD=|hw:CARD=)/i;

function isPlaceholderId(id: string): boolean {
  return !id || id === "default" || id === "communications";
}

function dedupeDevices(raw: MediaDeviceInfo[]): Device[] {
  // Pass 1: bucket by (kind, groupId). Within a bucket, the first entry
  // with a "clean" label wins; if none are clean, we keep the first entry
  // so the device is still selectable.
  const buckets = new Map<string, Device>();
  const order: string[] = [];

  for (const d of raw) {
    if (isPlaceholderId(d.deviceId)) continue;
    const labelRaw = d.label || `${d.kind} (${d.deviceId.slice(0, 8)}…)`;
    // Use groupId when present so all variants of the same physical card
    // collapse to one row. Fall back to deviceId so unique devices without
    // a groupId still appear once.
    const bucketKey = `${d.kind}:${d.groupId || d.deviceId}`;
    const isNoise = NOISE_LABEL_RE.test(labelRaw);
    const existing = buckets.get(bucketKey);

    if (!existing) {
      buckets.set(bucketKey, { deviceId: d.deviceId, label: labelRaw, kind: d.kind });
      order.push(bucketKey);
      continue;
    }
    // Prefer a clean label over a noisy one for the same physical device.
    if (NOISE_LABEL_RE.test(existing.label) && !isNoise) {
      buckets.set(bucketKey, { deviceId: d.deviceId, label: labelRaw, kind: d.kind });
    }
  }

  return order
    .map((k) => buckets.get(k)!)
    // Drop entries that survived but are still pure noise (e.g. a card whose
    // only enumerated form is "Monitor of …"). User has nothing useful here.
    .filter((d) => !NOISE_LABEL_RE.test(d.label));
}

function useDevices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [permissionGranted, setPermissionGranted] = useState(false);

  const refresh = async () => {
    const raw = await navigator.mediaDevices.enumerateDevices();
    setDevices(dedupeDevices(raw));
  };

  const requestPermissions = async () => {
    try {
      // Requesting getUserMedia populates device labels.
      const s = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      for (const t of s.getTracks()) t.stop();
      setPermissionGranted(true);
    } catch {
      // Camera may be denied but mic might work — try audio only.
      try {
        const s = await navigator.mediaDevices.getUserMedia({ audio: true });
        for (const t of s.getTracks()) t.stop();
        setPermissionGranted(true);
      } catch {/* blocked entirely */}
    }
    await refresh();
  };

  useEffect(() => {
    void refresh();
    navigator.mediaDevices.addEventListener("devicechange", refresh);
    return () => navigator.mediaDevices.removeEventListener("devicechange", refresh);
  }, []);

  return { devices, permissionGranted, requestPermissions, refresh };
}

function readPref(key: string): string {
  return localStorage.getItem(key) ?? "default";
}

function writePref(key: string, value: string): void {
  localStorage.setItem(key, value);
}

/** Apply speaker selection to all <audio> elements on the page (if supported). */
async function applySpeaker(deviceId: string): Promise<void> {
  if (!deviceId || deviceId === "default") return;
  const elements = document.querySelectorAll("audio");
  for (const el of elements) {
    // setSinkId is a non-standard Chromium API.
    const e = el as HTMLAudioElement & { setSinkId?: (id: string) => Promise<void> };
    if (typeof e.setSinkId === "function") {
      try { await e.setSinkId(deviceId); } catch {/* ignore */}
    }
  }
}

type CategoryRowProps = {
  category: Category;
  devices: Device[];
  hasLabels: boolean;
  onRequestPermissions: () => Promise<void>;
};

function CategoryRow({ category, devices, hasLabels, onRequestPermissions }: CategoryRowProps) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string>(() => readPref(category.storageKey));

  const filtered = devices.filter((d) => d.kind === category.kind);

  // If a remembered deviceId no longer enumerates (driver swap, USB unplug,
  // OS reboot), drop it back to "default" so the orb doesn't fail with a
  // mysterious "OverconstrainedError: deviceId" on the next mic open.
  useEffect(() => {
    if (!hasLabels) return;
    if (selected === "default") return;
    if (filtered.some((d) => d.deviceId === selected)) return;
    setSelected("default");
    writePref(category.storageKey, "default");
  }, [hasLabels, filtered, selected, category.storageKey]);

  const handleSelect = async (deviceId: string) => {
    setSelected(deviceId);
    writePref(category.storageKey, deviceId);
    if (category.kind === "audiooutput") {
      await applySpeaker(deviceId);
    }
    // Emit a custom event so VoicePanel can re-open getUserMedia with new deviceId.
    window.dispatchEvent(new CustomEvent("hosaka:devicechange", { detail: { kind: category.kind, deviceId } }));
    // Auto-collapse so a long list never traps the operator inside the row.
    setOpen(false);
  };

  const selectedLabel =
    filtered.find((d) => d.deviceId === selected)?.label ??
    (selected === "default" ? "system default" : selected.slice(0, 20) + "…");

  return (
    <div className="device-row">
      <button
        className={`device-row-header${open ? " device-row-header--open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="device-row-icon">{category.icon}</span>
        <span className="device-row-label">{category.label}</span>
        <span className="device-row-current">{selectedLabel}</span>
        <span className="device-row-chevron">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="device-row-body">
          {!hasLabels && (
            <button className="device-grant-btn" onClick={onRequestPermissions}>
              grant permissions to see device names
            </button>
          )}
          {filtered.length === 0 && hasLabels && (
            <div className="device-empty">no {category.label} devices found</div>
          )}
          {/* "system default" option */}
          <label className="device-option">
            <input
              type="radio"
              name={category.kind}
              value="default"
              checked={selected === "default"}
              onChange={() => void handleSelect("default")}
            />
            <span>system default</span>
          </label>
          {filtered.map((d) => (
            <label key={d.deviceId} className="device-option">
              <input
                type="radio"
                name={category.kind}
                value={d.deviceId}
                checked={selected === d.deviceId}
                onChange={() => void handleSelect(d.deviceId)}
              />
              <span>{d.label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function DevicePanel() {
  const { devices, permissionGranted, requestPermissions } = useDevices();
  const hasLabels = permissionGranted || devices.some((d) => !!d.label && !d.label.startsWith(d.kind));

  return (
    <div className="device-panel">
      <div className="device-panel-title">peripherals</div>
      {CATEGORIES.map((cat) => (
        <CategoryRow
          key={cat.kind}
          category={cat}
          devices={devices}
          hasLabels={hasLabels}
          onRequestPermissions={requestPermissions}
        />
      ))}
    </div>
  );
}

/** Exported helpers so VoicePanel can open getUserMedia with the stored device. */
export function getPreferredMicConstraints(): MediaTrackConstraints {
  const id = readPref("hosaka.device.mic");
  const base: MediaTrackConstraints = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  return id && id !== "default" ? { ...base, deviceId: { exact: id } } : base;
}

export function getPreferredCamConstraints(): MediaTrackConstraints {
  const id = readPref("hosaka.device.cam");
  return id && id !== "default" ? { deviceId: { exact: id } } : {};
}

export function getPreferredSpeakerId(): string {
  return readPref("hosaka.device.spk");
}
