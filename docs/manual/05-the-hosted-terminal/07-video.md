# 05.07 · the video tab

> _the loop continues. the loop does not require your attention._

The Video panel plays ambient short-form video. It exists primarily
because the appliance has a touchscreen and there is value in giving
the screen something to do when no one is at the keyboard.

---

## what plays

Whatever the playlist points at. The default playlist is bundled with
the SPA at `frontend/public/library/video-playlist.json` and contains
a mix of:

- TikTok shorts (embedded)
- YouTube shorts (embedded)
- Local mp4s (bundled or hosted)

On the appliance, the panel polls `/api/video/next` every few minutes
to advance the loop.

---

## controls

Minimal. Tap to play / pause. Swipe (or arrow-keys) to skip. There is
no scrub bar, no comments, no like button. This is _wallpaper that
happens to move_.

---

## customizing the playlist

If you've forked the repo:

1. Edit `frontend/public/library/video-playlist.json`:
   ```json
   [
     { "kind": "youtube", "id": "dQw4w9WgXcQ" },
     { "kind": "tiktok",  "url": "https://www.tiktok.com/@user/video/1234567890" },
     { "kind": "mp4",     "src": "/library/clips/orb.mp4" }
   ]
   ```
2. Push. Vercel rebuilds. Loop updates.

On the appliance, you can override the next-up logic by implementing
`/api/video/next` in your fork of `hosaka/web/server.py`.

---

## why video?

Because cyberdecks deserve idle ambience. Because the kiosk shouldn't
go dark. Because the orb needs something to look at, too.

> _the loop continues._
