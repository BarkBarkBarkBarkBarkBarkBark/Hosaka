import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";
import { useSyncedDoc } from "../sync/useSyncedDoc";

type Msg = {
  id: string;
  at: number;
  from: "operator" | "orb" | "system";
  text: string;
  status?: "sent" | "failed" | "pending";
};

type Config = {
  webhook: string;
  kind: "discord" | "slack" | "generic";
  username: string;
};

type MessagesDoc = {
  entries: Msg[];
  config: Config;
};

const MAX_MESSAGES = 200;
const INITIAL: MessagesDoc = {
  entries: [],
  config: { webhook: "", kind: "generic", username: "operator" },
};

function buildPayload(cfg: Config, text: string): unknown {
  switch (cfg.kind) {
    case "discord":
      return { content: text, username: cfg.username || "hosaka-operator" };
    case "slack":
      return { text, username: cfg.username || "hosaka-operator" };
    case "generic":
    default:
      return {
        text,
        username: cfg.username || "hosaka-operator",
        at: new Date().toISOString(),
        source: "hosaka-web-desktop",
      };
  }
}

function id(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function MessagesPanel() {
  const { t } = useTranslation("ui");
  const [doc, update] = useSyncedDoc<MessagesDoc>("messages", INITIAL);
  const messages = Array.isArray(doc.entries) ? doc.entries : [];
  const config = doc.config ?? INITIAL.config;
  const [draft, setDraft] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  const orbReplies = t("messages.orbReplies", { returnObjects: true }) as string[];

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages.length]);

  const push = (m: Msg) => {
    update((d) => {
      if (!Array.isArray(d.entries)) d.entries = [];
      d.entries.push(m);
      // Keep the log bounded. Dropping the oldest entry converges across
      // peers because Automerge sorts by actor+timestamp, not insertion.
      if (d.entries.length > MAX_MESSAGES) {
        d.entries.splice(0, d.entries.length - MAX_MESSAGES);
      }
    });
  };

  const setConfig = (patch: Partial<Config>) => {
    update((d) => {
      if (!d.config) d.config = { ...INITIAL.config };
      Object.assign(d.config, patch);
    });
  };

  const setStatus = (msgId: string, status: Msg["status"]) => {
    update((d) => {
      if (!Array.isArray(d.entries)) return;
      const i = d.entries.findIndex((m) => m.id === msgId);
      if (i >= 0) d.entries[i].status = status;
    });
  };

  const send = async () => {
    const text = draft.trim();
    if (!text) return;
    const mine: Msg = {
      id: id(),
      at: Date.now(),
      from: "operator",
      text,
      status: config.webhook ? "pending" : "sent",
    };
    push(mine);
    setDraft("");

    if (!config.webhook) {
      setTimeout(() => {
        push({
          id: id(),
          at: Date.now(),
          from: "orb",
          text:
            orbReplies[Math.floor(Math.random() * orbReplies.length)] ?? "...",
        });
      }, 600 + Math.random() * 800);
      setStatus(mine.id, "sent");
      return;
    }

    try {
      const res = await fetch(config.webhook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(config, text)),
      });
      const ok = res.ok;
      setStatus(mine.id, ok ? "sent" : "failed");
      if (!ok) {
        push({
          id: id(),
          at: Date.now(),
          from: "system",
          text: t("messages.webhookError", { status: res.status, statusText: res.statusText }),
        });
      }
    } catch (err: unknown) {
      setStatus(mine.id, "failed");
      push({
        id: id(),
        at: Date.now(),
        from: "system",
        text: t("messages.networkError", { message: (err as Error).message }),
      });
    }
  };

  const clearLog = () => update((d) => { d.entries = []; });

  return (
    <div className="messages-wrap">
      <div className="panel-header">
        <h2>
          <span className="panel-glyph">✉</span> {t("messages.heading")}
        </h2>
        <p className="panel-sub">
          {t("messages.sub")}
        </p>
      </div>

      <div className="messages-toolbar">
        <span className="dim">
          {t("messages.modeLabel")} <strong>{config.webhook ? config.kind : t("messages.offline")}</strong>
          {config.webhook ? (
            <> → {new URL(config.webhook).host}</>
          ) : (
            <> {t("messages.orbOnly")}</>
          )}
        </span>
        <div className="spacer" />
        <button className="btn btn-ghost" onClick={() => setShowSettings((s) => !s)}>
          {showSettings ? t("messages.closeSettings") : t("messages.openSettings")}
        </button>
        <button className="btn btn-ghost" onClick={clearLog}>
          {t("messages.clear")}
        </button>
      </div>

      {showSettings && (
        <div className="messages-settings">
          <label>
            <span>{t("messages.webhookLabel")}</span>
            <input
              type="url"
              placeholder={t("messages.webhookPlaceholder")}
              value={config.webhook}
              onChange={(e) =>
                setConfig({ webhook: e.target.value.trim() })
              }
            />
          </label>
          <label>
            <span>{t("messages.kindLabel")}</span>
            <select
              value={config.kind}
              onChange={(e) =>
                setConfig({ kind: e.target.value as Config["kind"] })
              }
            >
              <option value="generic">{t("messages.kindGeneric")}</option>
              <option value="discord">{t("messages.kindDiscord")}</option>
              <option value="slack">{t("messages.kindSlack")}</option>
            </select>
          </label>
          <label>
            <span>{t("messages.displayNameLabel")}</span>
            <input
              type="text"
              value={config.username}
              onChange={(e) => setConfig({ username: e.target.value })}
            />
          </label>
          <p className="dim small" dangerouslySetInnerHTML={{ __html: t("messages.storageNote") }} />
        </div>
      )}

      <div className="messages-log" ref={logRef}>
        {messages.length === 0 && (
          <div className="messages-empty dim">
            {t("messages.empty")}
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg msg-${m.from}`}>
            <div className="msg-meta">
              <span className="msg-from">{m.from}</span>
              <span className="msg-time">
                {new Date(m.at).toLocaleTimeString()}
              </span>
              {m.status && m.status !== "sent" && (
                <span className={`msg-status msg-status-${m.status}`}>
                  {m.status}
                </span>
              )}
            </div>
            <div className="msg-body">{m.text}</div>
          </div>
        ))}
      </div>

      <form
        className="messages-compose"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <textarea
          rows={2}
          placeholder={t("messages.placeholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="btn btn-primary" type="submit" disabled={!draft.trim()}>
          {t("messages.send")}
        </button>
      </form>
    </div>
  );
}
