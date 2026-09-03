---
name: hosaka-reading
description: >
  Inspect the real ebook library and open Foliate on this Hosaka field
  terminal. Use when someone asks what books are available, asks to read,
  browse books, open a title, open the reader, or launch Foliate.
---

# Hosaka Reading

Use the shared reading tools when they are available; do not guess titles or suggest invented paths.

## Requests

- “What books are available?” → call `list_books`, then summarize the titles.
- “Open the books” / “I want to read” / “Launch Foliate” → call `open_reader`.
- “Read Frankenstein” / “Open Walden” → call `open_reader` with that title.
- If several titles match, ask which one, then call `open_reader` again.
- If the request is ambiguous, list the books first and offer to open Foliate.

If the tools are missing (Picoclaw shell path):

```bash
ls ~/Books
hosaka launch foliate
```

Open a specific ebook with Foliate and the file path. Never pass `~/Books` itself as an argument — Foliate treats a directory as an unpacked EPUB.

The terminal command `/read` opens the same Books / Field History portal.
Field History is Hosaka lore; ebooks belong to Foliate.
