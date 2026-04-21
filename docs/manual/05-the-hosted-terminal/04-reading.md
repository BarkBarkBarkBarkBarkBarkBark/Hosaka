# 05.04 · the reading tab

```
collections — reading material from the signal
```

The Reading panel is now collection-based. Instead of listing individual
local markdown files, it lists collections of GitHub Pages content and
embeds the selected collection directly in the panel.

---

## opening reading

Two ways:

1. Click the **Reading** tab in the dock.
2. From the terminal:

```
/read            # list collections
/read lore       # open a collection in Reading
```

---

## current collections

Collections are configured in:

`frontend/public/reading/collections.json`

Current defaults:

- `lore`
- `manual`
- `thoozle`

Each collection entry defines title/summary/description, URL, and optional
aliases (used for `/read <value>` compatibility).

---

## how rendering works

- Sidebar: collection list from JSON config.
- Main pane: embedded GitHub Pages view (`iframe`) for selected collection.
- `open collection ↗` button opens the same URL in a new tab.

---

## note on adding collections

To add another collection, append another object in
`frontend/public/reading/collections.json` with a unique `id` and a valid
`https://` URL.

---

## next

- [05 · open loops](05-open-loops.md)
- [the lore chapter](../09-lore/README.md)
