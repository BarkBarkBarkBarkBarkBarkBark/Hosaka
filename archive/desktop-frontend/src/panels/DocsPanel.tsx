/**
 * DocsPanel — fullscreen markdown documents window.
 *
 * Browses, reads, and edits markdown under the operator's docs root
 * (default ~/.picoclaw/workspace/memory). Picoclaw + the voice agent
 * write here too via `/api/v1/docs/file` (PUT), so this panel is the
 * primary surface where agent-authored summaries, todo lists, and notes
 * land.
 *
 * Refresh strategy:
 *  • Refetch on mount and on `hosaka:doc-written` CustomEvent.
 *  • Light 10s poll while the panel is active (matches InboxPanel).
 *  • No focus hijack — agent writes surface here only when the operator
 *    chooses to look. Toast lives in App.tsx.
 *
 * Editor: plain <textarea> with a small toolbar that wraps selection in
 * markdown markers (heading / bold / italic / underline (HTML <u>) /
 * code / list / checkbox). Preview uses the existing `marked` renderer.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { marked } from "marked";

interface DocSummary {
  path: string;
  title: string;
  size: number;
  mtime: number;
}

interface DocReadResponse {
  path: string;
  body: string;
  mtime: number;
}

interface DocsPanelProps {
  active?: boolean;
}

marked.setOptions({ gfm: true, breaks: true });

const NEW_DOC_PLACEHOLDER = "# untitled\n\n";

export function DocsPanel({ active = true }: DocsPanelProps) {
  const [docs, setDocs] = useState<DocSummary[]>([]);
  const [root, setRoot] = useState<string>("");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [body, setBody] = useState<string>("");
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [treeOpen, setTreeOpen] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const refetch = useCallback(async () => {
    try {
      const r = await fetch("/api/v1/docs");
      if (!r.ok) throw new Error(`list failed (${r.status})`);
      const j = (await r.json()) as { root: string; docs: DocSummary[] };
      setDocs(j.docs);
      setRoot(j.root);
      setErr(null);
    } catch (e) {
      setErr(String((e as Error).message || e));
    }
  }, []);

  // Initial fetch + refresh on agent writes + slow poll while active.
  useEffect(() => {
    void refetch();
    const onWrite = () => { void refetch(); };
    window.addEventListener("hosaka:doc-written", onWrite as EventListener);
    return () => window.removeEventListener("hosaka:doc-written", onWrite as EventListener);
  }, [refetch]);

  useEffect(() => {
    if (!active) return;
    // Doc writes already fire `hosaka:doc-written` for instant refresh;
    // the timer is just a safety net. 30 s is plenty and keeps the Pi's
    // SD card from being walked every 10 s while the panel is open.
    const id = window.setInterval(() => { void refetch(); }, 30000);
    return () => window.clearInterval(id);
  }, [active, refetch]);

  // Auto-select newest doc on first load if nothing chosen.
  useEffect(() => {
    if (selectedPath || docs.length === 0) return;
    setSelectedPath(docs[0].path);
  }, [docs, selectedPath]);

  // Load selected file body.
  useEffect(() => {
    if (!selectedPath) { setBody(""); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`/api/v1/docs/file?path=${encodeURIComponent(selectedPath)}`);
        if (!r.ok) throw new Error(`read failed (${r.status})`);
        const j = (await r.json()) as DocReadResponse;
        if (cancelled) return;
        setBody(j.body);
        setDirty(false);
        setEditing(false);
        setErr(null);
      } catch (e) {
        if (!cancelled) setErr(String((e as Error).message || e));
      }
    })();
    return () => { cancelled = true; };
  }, [selectedPath]);

  // Render preview whenever body changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const html = await marked.parse(body || "");
      if (!cancelled) setPreviewHtml(html);
    })();
    return () => { cancelled = true; };
  }, [body]);

  const newDoc = useCallback(() => {
    const stamp = new Date().toISOString().slice(0, 10);
    const slug = `${stamp}-untitled.md`;
    setSelectedPath(slug);
    setBody(NEW_DOC_PLACEHOLDER);
    setEditing(true);
    setDirty(true);
  }, []);

  const save = useCallback(async () => {
    if (!selectedPath) return;
    setSaving(true);
    try {
      const r = await fetch("/api/v1/docs/file", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path: selectedPath, body, mode: "overwrite" }),
      });
      if (!r.ok) throw new Error(`save failed (${r.status})`);
      setDirty(false);
      setEditing(false);
      window.dispatchEvent(new CustomEvent("hosaka:doc-written", { detail: { path: selectedPath } }));
      await refetch();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setSaving(false);
    }
  }, [body, refetch, selectedPath]);

  const wrap = useCallback((before: string, after: string = before) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const sel = body.slice(start, end);
    const next = body.slice(0, start) + before + sel + after + body.slice(end);
    setBody(next);
    setDirty(true);
    requestAnimationFrame(() => {
      ta.focus();
      ta.selectionStart = start + before.length;
      ta.selectionEnd = end + before.length;
    });
  }, [body]);

  const linePrefix = useCallback((prefix: string) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    // find start of current line
    const lineStart = body.lastIndexOf("\n", start - 1) + 1;
    const next = body.slice(0, lineStart) + prefix + body.slice(lineStart);
    setBody(next);
    setDirty(true);
    requestAnimationFrame(() => {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = start + prefix.length;
    });
  }, [body]);

  const grouped = useMemo(() => {
    const map = new Map<string, DocSummary[]>();
    for (const d of docs) {
      const dir = d.path.includes("/") ? d.path.split("/").slice(0, -1).join("/") : "";
      const arr = map.get(dir) ?? [];
      arr.push(d);
      map.set(dir, arr);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [docs]);

  return (
    <div className="docs-wrap">
      <aside className={`docs-tree ${treeOpen ? "is-open" : ""}`}>
        <div className="docs-tree-head">
          <button
            type="button"
            className="docs-tree-toggle"
            aria-label={treeOpen ? "hide tree" : "show tree"}
            onClick={() => setTreeOpen((v) => !v)}
          >{treeOpen ? "◀" : "▶"}</button>
          <span className="docs-tree-title">documents</span>
          <button type="button" className="docs-new-btn" onClick={newDoc} title="new doc">+ new</button>
        </div>
        {treeOpen && (
          <>
            <div className="docs-tree-root" title={root}>{root || "…"}</div>
            <ul className="docs-tree-list">
              {grouped.length === 0 && (
                <li className="docs-tree-empty">no docs yet · ask the agent to write one</li>
              )}
              {grouped.map(([dir, items]) => (
                <li key={dir || "/"} className="docs-tree-group">
                  {dir && <div className="docs-tree-group-head">{dir}/</div>}
                  <ul>
                    {items.map((d) => (
                      <li
                        key={d.path}
                        className={`docs-tree-item ${selectedPath === d.path ? "is-active" : ""}`}
                      >
                        <button type="button" onClick={() => setSelectedPath(d.path)}>
                          <span className="docs-tree-item-title">{d.title}</span>
                          <span className="docs-tree-item-meta">{formatTime(d.mtime)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>

      <section className="docs-stage">
        <div className="docs-stage-head">
          <div className="docs-stage-title">
            <span className="docs-stage-glyph">▤</span>
            <span>{selectedPath || "select or create a doc"}</span>
            {dirty && <span className="docs-dirty-dot" title="unsaved">●</span>}
          </div>
          <div className="docs-stage-actions">
            {selectedPath && (
              <>
                <button
                  type="button"
                  className={`btn ${editing ? "" : "btn-ghost"}`}
                  onClick={() => setEditing((v) => !v)}
                >{editing ? "preview" : "edit"}</button>
                <button
                  type="button"
                  className="btn"
                  onClick={save}
                  disabled={!dirty || saving}
                >{saving ? "saving…" : "save"}</button>
              </>
            )}
          </div>
        </div>

        {err && <div className="docs-error">{err}</div>}

        {editing ? (
          <div className="docs-editor">
            <div className="docs-toolbar" role="toolbar" aria-label="markdown formatting">
              <button type="button" onClick={() => linePrefix("# ")} title="heading 1">H1</button>
              <button type="button" onClick={() => linePrefix("## ")} title="heading 2">H2</button>
              <button type="button" onClick={() => linePrefix("### ")} title="heading 3">H3</button>
              <span className="docs-toolbar-sep" />
              <button type="button" onClick={() => wrap("**")} title="bold"><b>B</b></button>
              <button type="button" onClick={() => wrap("*")} title="italic"><i>I</i></button>
              <button type="button" onClick={() => wrap("<u>", "</u>")} title="underline"><u>U</u></button>
              <button type="button" onClick={() => wrap("`")} title="inline code"><code>{`< >`}</code></button>
              <span className="docs-toolbar-sep" />
              <button type="button" onClick={() => linePrefix("- ")} title="bullet list">•</button>
              <button type="button" onClick={() => linePrefix("- [ ] ")} title="checkbox">☐</button>
              <button type="button" onClick={() => linePrefix("> ")} title="quote">❝</button>
            </div>
            <textarea
              ref={textareaRef}
              className="docs-textarea"
              value={body}
              onChange={(e) => { setBody(e.target.value); setDirty(true); }}
              spellCheck
              placeholder="# title\n\nstart writing…"
            />
          </div>
        ) : (
          <article
            className="docs-reader"
            // marked output is trusted: source is local fs the operator (or
            // their own picoclaw agent) controls. No third-party html.
            dangerouslySetInnerHTML={{ __html: previewHtml }}
          />
        )}
      </section>
    </div>
  );
}

function formatTime(epoch: number): string {
  const d = new Date(epoch * 1000);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return d.toISOString().slice(0, 10);
}
