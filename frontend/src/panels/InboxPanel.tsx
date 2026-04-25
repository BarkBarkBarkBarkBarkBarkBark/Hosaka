import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "../i18n";

type InboxEvent = {
  id: string;
  at: number;
  kind: "notify" | "ack";
  author: string;
  node_id: string;
  topic: string;
  severity: "info" | "success" | "warn" | "error";
  title: string;
  body: string;
  target: string;
  tags: string[];
  acked: boolean;
  ack_at?: number | null;
  ack_author?: string | null;
};

type InboxFeed = {
  chain_head: string;
  chain_ok: boolean;
  node_id: string;
  notifications: InboxEvent[];
};

const INITIAL_FORM = {
  title: "",
  body: "",
  topic: "general",
  severity: "info",
  tags: "",
};

export function InboxPanel() {
  const { t } = useTranslation("ui");
  const [feed, setFeed] = useState<InboxFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

  const refresh = useCallback(async () => {
    try {
      if (!feed) setLoading(true);
      const res = await fetch("/api/v1/inbox/events?limit=200");
      if (!res.ok) throw new Error(`http ${res.status}`);
      const data = (await res.json()) as InboxFeed;
      setFeed(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [feed]);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 10000);
    return () => clearInterval(id);
  }, [refresh]);

  const notifications = useMemo(() => feed?.notifications ?? [], [feed]);

  const acknowledge = useCallback(async (eventId: string) => {
    try {
      await fetch(`/api/v1/inbox/events/${eventId}/ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author: "operator" }),
      });
    } finally {
      void refresh();
    }
  }, [refresh]);

  const submit = useCallback(async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      await fetch("/api/v1/inbox/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.title.trim(),
          body: form.body.trim(),
          topic: form.topic.trim() || "general",
          severity: form.severity,
          tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean),
          author: "operator",
        }),
      });
      setComposerOpen(false);
      setForm(INITIAL_FORM);
      void refresh();
    } finally {
      setSaving(false);
    }
  }, [form, refresh]);

  return (
    <div className="messages-wrap">
      <div className="panel-header">
        <h2>
          <span className="panel-glyph">☰</span> {t("inbox.heading", "inbox")}
        </h2>
        <p className="panel-sub">{t("inbox.sub", "append-only notices that can gossip across your Hosaka nodes.")}</p>
      </div>

      <div className="messages-toolbar">
        <span className="dim small">
          {t("inbox.chain", "chain")}: <code>{feed?.chain_head?.slice(0, 12) ?? "—"}</code>
          {" · "}
          {feed?.chain_ok ? t("inbox.chainOk", "verified") : t("inbox.chainBad", "warning: chain mismatch")}
        </span>
        <div className="spacer" />
        <button className="btn btn-ghost" onClick={() => setComposerOpen((s) => !s)}>
          {composerOpen ? t("inbox.closeComposer", "close composer") : t("inbox.openComposer", "new notice")}
        </button>
        <button className="btn btn-ghost" onClick={() => void refresh()}>
          {t("inbox.refresh", "refresh")}
        </button>
      </div>

      {composerOpen && (
        <div className="messages-settings">
          <label>
            <span>{t("inbox.title", "title")}</span>
            <input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          </label>
          <label>
            <span>{t("inbox.body", "body")}</span>
            <textarea rows={3} value={form.body} onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))} />
          </label>
          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "1fr 1fr 1fr" }}>
            <label>
              <span>{t("inbox.topic", "topic")}</span>
              <input value={form.topic} onChange={(e) => setForm((f) => ({ ...f, topic: e.target.value }))} />
            </label>
            <label>
              <span>{t("inbox.severity", "severity")}</span>
              <select value={form.severity} onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}>
                <option value="info">info</option>
                <option value="success">success</option>
                <option value="warn">warn</option>
                <option value="error">error</option>
              </select>
            </label>
            <label>
              <span>{t("inbox.tags", "tags")}</span>
              <input value={form.tags} onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))} placeholder="ops, update" />
            </label>
          </div>
          <button className="btn btn-primary" disabled={saving || !form.title.trim()} onClick={() => void submit()}>
            {saving ? t("inbox.sending", "writing…") : t("inbox.post", "append notice")}
          </button>
        </div>
      )}

      <div className="messages-log">
        {loading && !feed && <div className="messages-empty dim">{t("inbox.loading", "loading inbox…")}</div>}
        {error && <div className="messages-empty dim">{t("inbox.error", "could not load inbox")}: {error}</div>}
        {!loading && !error && notifications.length === 0 && (
          <div className="messages-empty dim">{t("inbox.empty", "no notifications yet.")}</div>
        )}
        {notifications.map((item) => (
          <div key={item.id} className={`msg msg-system`}>
            <div className="msg-meta">
              <span className={`msg-status msg-status-${item.severity}`}>{item.severity}</span>
              <span className="msg-from">{item.topic}</span>
              <span className="msg-time">{new Date(item.at).toLocaleString()}</span>
              <span className="msg-from">{item.author}</span>
            </div>
            <div className="msg-body">
              <strong>{item.title}</strong>
              {item.body && <div style={{ marginTop: 6 }}>{item.body}</div>}
              {!!item.tags.length && <div className="dim small" style={{ marginTop: 6 }}>#{item.tags.join(" #")}</div>}
              <div className="dim small" style={{ marginTop: 6 }}>
                node <code>{item.node_id.slice(0, 8)}</code>
                {item.acked ? (
                  <> · {t("inbox.ackedBy", "acked by")} {item.ack_author ?? "operator"}</>
                ) : (
                  <> · {t("inbox.unacked", "unacked")}</>
                )}
              </div>
            </div>
            {!item.acked && (
              <div className="messages-toolbar" style={{ paddingTop: 8 }}>
                <button className="btn btn-ghost" onClick={() => void acknowledge(item.id)}>
                  {t("inbox.ack", "acknowledge")}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}