/**
 * MusicPanel — Hosaka radio. HTML5 <audio> player against a tiny
 * client-side library of public-domain / CC-BY audio pulled from the
 * Internet Archive. Works the same in browser dev and in the Electron
 * kiosk, which is why we picked HTML5 audio over an mpv subprocess for
 * the MVP. (mpv driver can be slotted in later behind the same Track[]
 * surface.)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearLibrary,
  getLibrary,
  populateLibrary,
  type Track,
} from "../apps/library";

type Status = { kind: "idle" | "info" | "ok" | "error"; text: string };

export function MusicPanel() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [tracks, setTracks] = useState<Track[]>(() => getLibrary());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: "idle", text: "" });

  const refresh = useCallback(() => setTracks(getLibrary()), []);

  useEffect(() => {
    window.addEventListener("hosaka:radio-library-changed", refresh);
    return () => window.removeEventListener("hosaka:radio-library-changed", refresh);
  }, [refresh]);

  const active = tracks.find((t) => t.id === activeId) ?? null;

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !active) return;
    el.src = active.audioUrl;
    el.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }, [active]);

  async function onPopulate(genre: "classical" | "jazz") {
    setBusy(true);
    setStatus({ kind: "info", text: `pulling ${genre} from internet archive…` });
    const res = await populateLibrary(genre, 6);
    setBusy(false);
    refresh();
    if (res.added.length === 0) {
      setStatus({ kind: "error", text: res.message ?? "no tracks added (IA returned no usable audio)." });
      return;
    }
    setStatus({
      kind: "ok",
      text: `added ${res.added.length} ${genre} track(s). library has ${res.total}.`,
    });
  }

  function onPlay(track: Track) {
    setActiveId(track.id);
  }

  function onPause() {
    audioRef.current?.pause();
    setPlaying(false);
  }

  function onResume() {
    audioRef.current?.play().then(() => setPlaying(true)).catch(() => undefined);
  }

  function onClear() {
    clearLibrary();
    refresh();
    setActiveId(null);
    setStatus({ kind: "info", text: "library cleared." });
  }

  return (
    <div className="desktop-panel desktop-panel--directory">
      <div className="panel-header">
        <h2><span className="panel-glyph">♫</span> hosaka radio</h2>
        <p className="panel-sub">
          public-domain &amp; cc-licensed audio from the internet archive.
        </p>
      </div>

      <div style={{ padding: "0.5rem 1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" className="btn" disabled={busy} onClick={() => void onPopulate("classical")}>
          + populate classical
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => void onPopulate("jazz")}>
          + populate jazz
        </button>
        <button type="button" className="btn" disabled={busy || tracks.length === 0} onClick={onClear}>
          clear library
        </button>
      </div>

      {status.text && (
        <div
          style={{
            padding: "0.4rem 1rem",
            color: status.kind === "error" ? "#f88" : status.kind === "ok" ? "#9cf" : "#ccc",
            fontSize: "0.9em",
          }}
        >
          {status.text}
        </div>
      )}

      <div style={{ padding: "0.5rem 1rem" }}>
        <audio
          ref={audioRef}
          controls
          style={{ width: "100%" }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
        {active && (
          <div className="dim" style={{ fontSize: "0.85em", marginTop: "0.3rem" }}>
            now playing: <strong>{active.title}</strong> — {active.creator}
            {" · "}
            <a href={active.detailsUrl} target="_blank" rel="noreferrer">{active.license || "source"}</a>
            {" · "}
            <span>{active.attribution}</span>
          </div>
        )}
        {active && (
          <div style={{ marginTop: "0.3rem", display: "flex", gap: "0.4rem" }}>
            <button type="button" className="btn" onClick={playing ? onPause : onResume}>
              {playing ? "pause" : "play"}
            </button>
          </div>
        )}
      </div>

      <ul style={{ listStyle: "none", margin: 0, padding: "0 1rem 1rem" }}>
        {tracks.length === 0 && (
          <li className="dim" style={{ padding: "0.5rem 0", fontSize: "0.9em" }}>
            library is empty — populate classical or jazz above to seed it.
          </li>
        )}
        {tracks.map((track) => (
          <li
            key={track.id}
            style={{
              padding: "0.5rem 0",
              borderBottom: "1px solid rgba(255,255,255,0.05)",
              display: "flex",
              gap: "0.75rem",
              alignItems: "center",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div><strong>{track.title}</strong></div>
              <div className="dim" style={{ fontSize: "0.85em" }}>
                {track.creator} · {track.genre} · {track.license || "see source"}
              </div>
            </div>
            <button
              type="button"
              className="btn"
              onClick={() => onPlay(track)}
              aria-pressed={activeId === track.id}
            >
              {activeId === track.id && playing ? "playing" : "play"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
