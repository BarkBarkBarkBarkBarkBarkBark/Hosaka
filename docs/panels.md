# Adding a new panel (canonical recipe)

The Hosaka kiosk is a single React SPA with a dock of tabs across the top.
Each tab is a "panel" — a self-contained chunk that lazy-loads on first tap
and stays mounted afterwards so its state survives tab switching.

This is the exact 6-step recipe. Follow it in order. Every existing panel
(`TerminalPanel`, `ReadingPanel`, `TodoPanel`, `VideoPanel`, `MessagesPanel`,
`GamesPanel`, `WikiPanel`, `WebPanel`, `BooksPanel`) is built this way.

**`WebPanel`** — browser-surface + preset shortcuts. Internal Hosaka targets
render in-panel; arbitrary external sites launch through the current browser
adapter (web fallback/new tab today, native/remote adapters later).

## File map

```
frontend/
├── src/
│   ├── App.tsx                 ← shell: registers panels, owns active tab
│   ├── panels/
│   │   ├── XxxPanel.tsx        ← (1) the panel component lives here
│   │   └── …
│   └── styles/
│       └── app.css             ← (5) panel-scoped CSS appended here
└── public/
    └── locales/
        └── <lang>/ui.json      ← (6) i18n keys (at minimum en/)
```

## The 6 steps

### 1. Create `src/panels/XxxPanel.tsx`

Conventions:

- Export a **named** component: `export function XxxPanel(...)`.
- Props are `{ active: boolean }` if the panel needs to react to becoming
  visible (resize a canvas, focus an input, start an animation loop). Omit
  props entirely if it doesn't.
- Bail out cheap when not visible if it owns an animation loop / interval
  that should pause: `if (!active) return null;` is fine; or gate the
  `requestAnimationFrame` itself.
- Persistent panel state goes in `localStorage` under `hosaka.<panel>.v1`.
  See `TodoPanel` for the canonical pattern.
- Cross-panel commands come in via `window.addEventListener("hosaka:<verb>", …)`.
  See `ReadingPanel` (`hosaka:read`) and `VideoPanel` (`hosaka:video`).

Skeleton:

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "../i18n";

type Props = { active: boolean };

export function XxxPanel({ active }: Props) {
  const { t } = useTranslation("ui");
  // ...state, effects gated on `active` if needed...

  return (
    <div className="xxx-panel">
      <header className="panel-header">
        <h2><span className="panel-glyph">◆</span> {t("xxx.heading")}</h2>
        <p className="panel-sub">{t("xxx.sub")}</p>
      </header>
      {/* panel body */}
    </div>
  );
}
```

### 2. Lazy-import in `App.tsx`

First-paint of the kiosk only ships the shell + the default tab. Every
other panel is a separate chunk:

```tsx
const XxxPanel = lazy(() =>
  import("./panels/XxxPanel").then((m) => ({ default: m.XxxPanel })),
);
```

### 3. Extend the `PanelId` union

```tsx
export type PanelId = "terminal" | "messages" | "reading" | "todo" | "video" | "xxx";
```

### 4. Add a dock entry

In the `panels` `useMemo` array. Glyph is one or two ASCII / box-drawing
characters; keep it monospace-friendly:

```tsx
{ id: "xxx", label: t("tabs.xxx"), glyph: "◆" },
```

### 5. Add a render slot inside `<main className="hosaka-stage">`

The `visited` set ensures the chunk only loads after the operator first
taps the tab, but stays mounted afterwards (state preserved):

```tsx
{visited.has("xxx") && (
  <div className="hosaka-panel" hidden={active !== "xxx"}>
    <XxxPanel active={active === "xxx"} />
  </div>
)}
```

### 6. Add CSS + i18n

**CSS** — append a section to `src/styles/app.css`:

```css
/* ── xxx panel ───────────────────────────────────────────── */
.xxx-panel {
  height: 100%;
  display: flex;
  /* … */
}
```

Use the existing CSS variables (`--bg-0..3`, `--fg-0..3`, `--amber`, `--cyan`,
`--violet`, `--border`, `--font-mono`, `--font-ui`). Don't introduce new
ones unless the design system actually grew.

**i18n** — at minimum add to `public/locales/en/ui.json`:

```json
{
  "tabs": { "xxx": "Xxx" },
  "xxx": { "heading": "xxx", "sub": "what this panel is for" }
}
```

Other locales (`es/`, `fr/`, `it/`, `ja/`, `pt/`) fall back to `en` for
missing keys, so adding `en` first is enough to ship; translate when you
have the strings.

## Cross-panel command bus

The terminal can drive other panels via `CustomEvent`:

| Event                    | Payload          | Handled by      |
|--------------------------|------------------|-----------------|
| `hosaka:open-tab`        | `PanelId`        | `App.tsx`       |
| `hosaka:open-settings`   | `void`           | `App.tsx`       |
| `hosaka:ui-changed`      | `void`           | `App.tsx`, `TerminalPanel` |
| `hosaka:read`            | `slug: string`   | `ReadingPanel`  |
| `hosaka:todo-add`        | `text: string`   | `TodoPanel`     |
| `hosaka:video`           | `url: string`    | `VideoPanel`    |
| `hosaka:web-preset`      | `presetId: string` | `WebPanel`    |
| `hosaka:web-open`        | `target: string` | `WebPanel`      |
| `hosaka:books-search`    | `query: string`  | `BooksPanel`    |

Add new events here when you wire them up. Keep the namespace `hosaka:*`
and use `kebab-case`. Detail payloads should be JSON-serialisable so the
shell command parser can dispatch them from a single string.

## Don'ts

- Don't import the panel **eagerly** in `App.tsx`. It defeats the
  ~700 KB → ~per-panel-chunk savings the kiosk depends on.
- Don't put panel CSS in its own file — Vite would emit a separate stylesheet
  per panel and FOUC the kiosk every time you switch tabs. Append to
  `styles/app.css`.
- Don't use `react-router`. The dock IS the router. Tab state is in
  `App.tsx` `useState<PanelId>`.
- Don't fetch on every render. Either fetch in a one-shot `useEffect(…, [])`
  and cache in component state, or persist to `localStorage` under
  `hosaka.<panel>.v1`.
- Don't unmount your panel when `active` flips false. The shell hides it
  with `hidden={…}` so state, scroll position, typing buffers, xterm
  scrollback all survive. Just pause expensive loops.

## Sizing

- Total panel chunk should be **< 50 KB minified** for a "small" panel
  (Tetris, Wiki, Todo).
- A "large" panel that pulls in a vendor library (xterm, marked, a player)
  is allowed to be bigger but should stay under ~500 KB and MUST be
  lazy-imported (`React.lazy`).
- If you need a heavy library only for one feature, dynamic-import it
  inside the panel itself, not at module top-level.
