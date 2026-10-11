/**
 * VideoPanel — streaming short-video feed for the cyberdeck.
 *
 * Primary source: TikTok oEmbed / iframe embeds (no API key required).
 * Fallback: a local/curated playlist JSON at /library/video-playlist.json
 *           with entries { url: string, title: string, source: string }.
 *
 * The panel auto-advances through the playlist on video end, or the user
 * can swipe / tap the ‹ › arrows. Touch-swipe left/right also works.
 *
 * For the 800×480 kiosk: videos are letter/pillar-boxed in a black stage.
 * TikTok embeds use their responsive iframe; MP4 clips use <video>.
 */

import { useEffect, useRef, useState } from "react";

type VideoEntry = {
  url: string;
  title: string;
  source: "tiktok" | "mp4" | "youtube-short";
};

type EmbedKind = "tiktok" | "youtube-short" | "mp4";

function detectKind(url: string): EmbedKind {
  if (url.includes("tiktok.com")) return "tiktok";
  if (url.includes("youtube.com/shorts") || url.includes("youtu.be")) return "youtube-short";
  return "mp4";
}

function tiktokEmbedUrl(url: string): string {
  // Extract video ID from various TikTok URL shapes:
  //   https://www.tiktok.com/@user/video/1234567890
  //   https://vm.tiktok.com/ABCDE/
  const match = url.match(/\/video\/(\d+)/);
  if (match) return `https://www.tiktok.com/embed/v2/${match[1]}`;
  // If it's already an embed URL, return as-is
  if (url.includes("/embed/")) return url;
  return url;
}

function youtubeShortEmbedUrl(url: string): string {
  // https://youtube.com/shorts/VIDEO_ID  →  embed
  const match = url.match(/shorts\/([a-zA-Z0-9_-]+)/);
  if (match) return `https://www.youtube.com/embed/${match[1]}?autoplay=1&loop=1&mute=1`;
  const watchMatch = url.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]+)/);
  if (watchMatch) return `https://www.youtube.com/embed/${watchMatch[1]}?autoplay=1&loop=1&mute=1`;
  return url;
}

const BUILTIN_PLAYLIST: VideoEntry[] = [
  // Seed with a few public-domain / creative-commons short clips from archive.org
  {
    url: "https://archive.org/download/BigBuckBunny_124/Content/big_buck_bunny_720p_surround.mp4",
    title: "big buck bunny",
    source: "mp4",
  },
  {
    url: "https://archive.org/download/ElephantsDream/ed_1024_512kb.mp4",
    title: "elephants dream",
    source: "mp4",
  },
];

export function VideoPanel({ active }: { active: boolean }) {
  const [playlist, setPlaylist] = useState<VideoEntry[]>(BUILTIN_PLAYLIST);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // touch-swipe state
  const touchStartX = useRef<number | null>(null);

  // ── load curated playlist ───────────────────────────────────────────────
  useEffect(() => {
    fetch("/library/video-playlist.json")
      .then((r) => r.ok ? r.json() : null)
      .then((data: VideoEntry[] | null) => {
        if (data && Array.isArray(data) && data.length > 0) {
          setPlaylist(data);
        }
      })
      .catch(() => {/* use builtin */})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setLoading(false); }, [playlist]);

  // ── listen for shell /video command ────────────────────────────────────
  useEffect(() => {
    const handler = (e: Event) => {
      const url = (e as CustomEvent<string>).detail;
      if (!url) return;
      const kind = detectKind(url);
      setPlaylist((prev) => [{ url, title: "injected", source: kind }, ...prev]);
      setIdx(0);
    };
    window.addEventListener("hosaka:video", handler as EventListener);
    return () => window.removeEventListener("hosaka:video", handler as EventListener);
  }, []);

  // ── poll /api/video/next for terminal-injected URLs ─────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      fetch("/api/video/next")
        .then((r) => r.ok ? r.json() : null)
        .then((data: { url?: string } | null) => {
          if (data?.url) {
            const kind = detectKind(data.url);
            setPlaylist((prev) => [{ url: data.url!, title: "injected", source: kind }, ...prev]);
            setIdx(0);
          }
        })
        .catch(() => {/* server not available */});
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const entry = playlist[idx] ?? null;
  const kind: EmbedKind = entry ? detectKind(entry.url) : "mp4";

  const prev = () => setIdx((i) => (i - 1 + playlist.length) % playlist.length);
  const next = () => setIdx((i) => (i + 1) % playlist.length);

  if (!active) return null;

  return (
    <div
      className="video-panel"
      onTouchStart={(e) => { touchStartX.current = e.touches[0].clientX; }}
      onTouchEnd={(e) => {
        if (touchStartX.current === null) return;
        const dx = e.changedTouches[0].clientX - touchStartX.current;
        if (dx > 60) prev();
        else if (dx < -60) next();
        touchStartX.current = null;
      }}
    >
      {/* top bar */}
      <div className="video-topbar">
        <span className="video-counter">
          {playlist.length > 0 ? `${idx + 1} / ${playlist.length}` : "—"}
        </span>
        <span className="video-title">{entry?.title ?? ""}</span>
        <div className="video-nav">
          <button className="btn btn-ghost" onClick={prev} aria-label="previous">◄</button>
          <button className="btn btn-ghost" onClick={next} aria-label="next">►</button>
        </div>
      </div>

      {/* stage */}
      <div className="video-stage">
        {loading && (
          <div className="video-loading">loading feed…</div>
        )}

        {!loading && !entry && (
          <div className="video-empty">
            <p>no videos in playlist.</p>
            <p className="dim small">
              add entries to <code>/library/video-playlist.json</code><br />
              or use <code>/video &lt;url&gt;</code> in the terminal.
            </p>
          </div>
        )}

        {!loading && entry && kind === "mp4" && (
          <video
            ref={videoRef}
            key={entry.url}
            className="video-player"
            src={entry.url}
            autoPlay
            loop
            playsInline
            controls={false}
            onEnded={next}
          />
        )}

        {!loading && entry && (kind === "tiktok" || kind === "youtube-short") && (
          <iframe
            key={entry.url}
            className="video-iframe"
            src={kind === "tiktok" ? tiktokEmbedUrl(entry.url) : youtubeShortEmbedUrl(entry.url)}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
            frameBorder="0"
            title={entry.title}
          />
        )}
      </div>

      {/* playlist rail */}
      <div className="video-rail">
        {playlist.map((v, i) => (
          <button
            key={`${v.url}-${i}`}
            className={`video-rail-item ${i === idx ? "is-active" : ""}`}
            onClick={() => setIdx(i)}
            title={v.title}
          >
            <span className="video-rail-source">{v.source}</span>
            <span className="video-rail-title">{v.title}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
