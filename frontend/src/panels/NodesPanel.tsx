/**
 * NodesPanel — Tailscale onboarding + list of other Hosaka devices on
 * this tailnet. Gated server-side by `nodes_enabled` in /api/health so
 * the hosted Vercel build never mounts it.
 *
 * Three states:
 *   - tailscale not installed        → install hint card
 *   - installed but not logged in    → "sign in to tailnet" button + SSE flow
 *   - connected                      → self card + peer list
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";

type TailscaleStatus = {
  installed: boolean;
  connected: boolean;
  hostname?: string;
  dns_name?: string;
  ip?: string;
  os?: string;
  peer_count?: number;
};

type NodesResponse = {
  installed: boolean;
  connected: boolean;
  self: TailscaleStatus | null;
  nodes: Peer[];
};

type Peer = {
  hostname: string;
  dns_name?: string;
  ip: string;
  online: boolean;
  os?: string;
  last_seen?: string;
  reachable?: boolean;
  commit?: string;
};

type JoinState =
  | { kind: "idle" }
  | { kind: "waiting" }
  | { kind: "url"; url: string }
  | { kind: "done" }
  | { kind: "error"; msg: string };

export function NodesPanel() {
  const { t } = useTranslation("ui");
  const [resp, setResp] = useState<NodesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [join, setJoin] = useState<JoinState>({ kind: "idle" });
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/nodes");
      setResp((await r.json()) as NodesResponse);
    } catch {
      setResp({ installed: false, connected: false, self: null, nodes: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    // Light polling: every 15s we re-probe peers so online/offline status
    // drifts in with real-time-ish feel. Cheap — most Hosaka nets are <10 nodes.
    const id = setInterval(() => void refresh(), 15000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  const beginJoin = useCallback(() => {
    // EventSource only supports GET, so we kick the POST endpoint ourselves
    // via fetch + ReadableStream and parse SSE frames by hand. Tiny parser.
    setJoin({ kind: "waiting" });

    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await fetch("/api/tailscale/up", {
          method: "POST",
          signal: ctrl.signal,
        });
        if (!res.body) throw new Error("no body");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          // SSE frames are separated by a blank line.
          let idx = buf.indexOf("\n\n");
          while (idx !== -1) {
            const frame = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const evt = parseFrame(frame);
            if (evt.event === "login_url" && evt.data) {
              setJoin({ kind: "url", url: evt.data });
            } else if (evt.event === "done") {
              if (evt.data === "ok") {
                setJoin({ kind: "done" });
                void refresh();
              } else {
                setJoin({ kind: "error", msg: evt.data });
              }
              ctrl.abort();
            }
            idx = buf.indexOf("\n\n");
          }
        }
      } catch (e) {
        if ((e as { name?: string }).name !== "AbortError") {
          setJoin({ kind: "error", msg: (e as Error).message });
        }
      }
    })();
  }, [refresh]);

  const copy = useCallback((value: string, key: string) => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 1200);
    });
  }, []);

  const logout = useCallback(async () => {
    if (!window.confirm(t("nodes.logoutConfirm"))) return;
    try {
      await fetch("/api/tailscale/logout", { method: "POST" });
    } finally {
      void refresh();
    }
  }, [refresh, t]);

  return (
    <div className="nodes-wrap">
      <header className="panel-header">
        <h2>
          <span className="panel-glyph">◈</span> {t("nodes.heading")}
        </h2>
        <p className="panel-sub">{t("nodes.sub")}</p>
      </header>

      <div className="nodes-body">
        {loading && !resp && <p className="nodes-loading">…</p>}

        {resp && !resp.installed && (
          <section className="nodes-card nodes-install">
            <h3>{t("nodes.installHeading")}</h3>
            <p>{t("nodes.installBody")}</p>
            <pre className="nodes-code">{t("nodes.installMac")}</pre>
            <pre className="nodes-code">{t("nodes.installLinux")}</pre>
            <p>
              <a href="https://tailscale.com/download" target="_blank" rel="noreferrer">
                {t("nodes.installDocs")}
              </a>
            </p>
          </section>
        )}

        {resp && resp.installed && !resp.connected && (
          <section className="nodes-card nodes-offline">
            <h3>{t("nodes.offlineHeading")}</h3>
            <p>{t("nodes.offlineBody")}</p>

            {join.kind === "idle" && (
              <button className="btn" onClick={beginJoin}>
                {t("nodes.joinBtn")}
              </button>
            )}
            {join.kind === "waiting" && <p className="nodes-loading">{t("nodes.joining")}</p>}
            {join.kind === "url" && (
              <div className="nodes-joinurl">
                <a href={join.url} target="_blank" rel="noreferrer" className="btn">
                  {t("nodes.joinUrl")}
                </a>
                <button
                  className="btn btn-ghost"
                  onClick={() => copy(join.url, "joinurl")}
                >
                  {copiedKey === "joinurl" ? t("nodes.joinCopied") : t("nodes.joinCopy")}
                </button>
                <code className="nodes-url">{join.url}</code>
              </div>
            )}
            {join.kind === "done" && <p className="nodes-ok">{t("nodes.joinDone")}</p>}
            {join.kind === "error" && (
              <p className="nodes-err">{t("nodes.joinError", { msg: join.msg })}</p>
            )}
          </section>
        )}

        {resp && resp.connected && resp.self && (
          <>
            <section className="nodes-card nodes-self">
              <h3>{t("nodes.selfHeading")}</h3>
              <dl className="nodes-dl">
                <dt>{t("nodes.selfHostname")}</dt>
                <dd>{resp.self.hostname ?? "—"}</dd>
                <dt>{t("nodes.selfIp")}</dt>
                <dd>
                  <code>{resp.self.ip ?? "—"}</code>
                </dd>
                {resp.self.dns_name && (
                  <>
                    <dt>{t("nodes.selfDns")}</dt>
                    <dd>
                      <code>{resp.self.dns_name}</code>
                    </dd>
                  </>
                )}
              </dl>
              <button className="btn btn-ghost" onClick={logout}>
                {t("nodes.logout")}
              </button>
            </section>

            <section className="nodes-card">
              <div className="nodes-peers-head">
                <h3>{t("nodes.peersHeading")}</h3>
                <button className="btn btn-ghost" onClick={() => void refresh()}>
                  {t("nodes.refresh")}
                </button>
              </div>

              {resp.nodes.length === 0 && (
                <p className="nodes-empty">{t("nodes.peersEmpty")}</p>
              )}

              {resp.nodes.map((p) => (
                <div
                  key={p.ip}
                  className={`nodes-peer ${p.online ? "is-online" : "is-offline"} ${
                    p.reachable ? "is-hosaka" : ""
                  }`}
                >
                  <span className="nodes-peer-dot" aria-hidden>
                    {p.reachable ? "◉" : p.online ? "○" : "·"}
                  </span>
                  <div className="nodes-peer-main">
                    <span className="nodes-peer-host">{p.hostname || p.ip}</span>
                    <span className="nodes-peer-meta">
                      <code>{p.ip}</code>
                      {" · "}
                      {p.online ? t("nodes.peerOnline") : t("nodes.peerOffline")}
                      {!p.reachable && p.online && (
                        <> {" · "} <em>{t("nodes.peerNotHosaka")}</em></>
                      )}
                    </span>
                  </div>
                  <div className="nodes-peer-actions">
                    {p.reachable && (
                      <a
                        className="btn btn-ghost"
                        href={`http://${p.ip}:8421/`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {t("nodes.peerOpen")}
                      </a>
                    )}
                    <button
                      className="btn btn-ghost"
                      onClick={() => copy(p.ip, `peer-${p.ip}`)}
                    >
                      {copiedKey === `peer-${p.ip}`
                        ? t("nodes.peerCopied")
                        : t("nodes.peerCopy")}
                    </button>
                  </div>
                </div>
              ))}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function parseFrame(frame: string): { event: string; data: string } {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  return { event, data: dataLines.join("\n") };
}
