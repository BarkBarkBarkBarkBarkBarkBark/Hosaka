import { useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";

type Value = string | number | boolean;
type Inputs = Record<string, Value>;
type Component =
  | { type: "Stack"; children: Component[] }
  | { type: "Heading" | "Text"; text: string }
  | { type: "Button"; label: string; action: string; params?: Record<string, string> }
  | { type: "TextInput"; id: string; label: string; default?: string }
  | { type: "NumberInput"; id: string; label: string; default?: number }
  | { type: "Checkbox"; id: string; label: string; default?: boolean }
  | { type: "Select"; id: string; label: string; options: string[]; default?: string }
  | { type: "Result" | "Error" | "Status"; bind: string }
  | { type: "Table"; bind: string; columns: string[] };
type Entry = {
  id: string; name: string; version: string; menu: { label: string; order: number };
  execution_available: boolean; execution_reason: string | null;
};
type Catalog = { extensions: Entry[]; invalid_package_count: number; safe_mode: boolean };
type ExtensionView = {
  id: string; name: string; digest: string;
  view: { version: 1; view: Component };
  actions: Record<string, { description: string; input_keys: string[] | null }>;
  execution_available: boolean; execution_reason: string | null;
};
type Invocation = {
  ok: boolean; invocation_id: string;
  result: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
};

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1/extensions${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body), signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail
    : typeof result.error?.message === "string" ? result.error.message : `HTTP ${response.status}`);
  return result;
}

function text(value: unknown): string {
  if (value === undefined || value === null) return "";
  const rendered = typeof value === "string" ? value : JSON.stringify(value) ?? "[unsupported value]";
  return rendered.replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g,
    (character) => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`);
}

function defaults(node: Component, inputs: Inputs = {}): Inputs {
  if (node.type === "Stack") node.children.forEach((child) => defaults(child, inputs));
  if (node.type === "TextInput") inputs[node.id] = node.default ?? "";
  if (node.type === "NumberInput") inputs[node.id] = node.default ?? 0;
  if (node.type === "Checkbox") inputs[node.id] = node.default ?? false;
  if (node.type === "Select") inputs[node.id] = node.default ?? node.options[0];
  return inputs;
}

function Renderer({ node, inputs, update, result, busy, enabled, execute }: {
  node: Component; inputs: Inputs; update: (id: string, value: Value) => void;
  result: Record<string, unknown> | null; busy: boolean; enabled: boolean;
  execute: (action: string, bindings?: Record<string, string>) => void;
}) {
  const { t } = useTranslation("gui");
  function binding(reference: string): unknown {
    const [scope, field] = reference.split(".");
    return scope === "params" ? (Object.hasOwn(inputs, field) ? inputs[field] : undefined)
      : result && Object.hasOwn(result, field) ? result[field] : undefined;
  }
  if (node.type === "Stack") return <div className="deck-extension-stack">{node.children.map((child, index) =>
    <Renderer key={index} node={child} inputs={inputs} update={update} result={result} busy={busy} enabled={enabled} execute={execute} />)}</div>;
  if (node.type === "Heading") return <h2>{text(node.text)}</h2>;
  if (node.type === "Text") return <p>{text(node.text)}</p>;
  if (node.type === "Button") return <button disabled={busy || !enabled} onClick={() => execute(node.action, node.params)}>{text(node.label)}</button>;
  if (node.type === "TextInput") return <label>{text(node.label)}<input disabled={busy} maxLength={2048} value={String(inputs[node.id] ?? "")}
    onChange={(event) => update(node.id, event.target.value)} /></label>;
  if (node.type === "NumberInput") return <label>{text(node.label)}<input type="number" disabled={busy} min={-1e12} max={1e12}
    value={String(inputs[node.id] ?? "")} onChange={(event) => {
      update(node.id, Number.isFinite(event.target.valueAsNumber) ? event.target.valueAsNumber : "");
    }} /></label>;
  if (node.type === "Checkbox") return <label className="deck-checkbox"><input type="checkbox" disabled={busy} checked={inputs[node.id] === true}
    onChange={(event) => update(node.id, event.target.checked)} />{text(node.label)}</label>;
  if (node.type === "Select") return <label>{text(node.label)}<select disabled={busy} value={String(inputs[node.id] ?? node.options[0])}
    onChange={(event) => update(node.id, event.target.value)}>{node.options.map((option) => <option key={option} value={option}>{text(option)}</option>)}</select></label>;
  if (node.type === "Table") {
    const rows = binding(node.bind);
    if (!Array.isArray(rows) || rows.length === 0) return null;
    return <div className="deck-extension-table"><table><thead><tr>{node.columns.map((column) => <th key={column}>{text(column)}</th>)}</tr></thead>
      <tbody>{rows.slice(0, 128).map((row: unknown, index) => <tr key={index}>{node.columns.map((column) =>
        <td key={column}>{text(typeof row === "object" && row !== null && Object.hasOwn(row, column) ? Reflect.get(row, column) : "")}</td>)}</tr>)}</tbody></table>
      {rows.length > 128 && <p className="deck-hint">{t("extensionsRowsTruncated")}</p>}</div>;
  }
  if (node.type === "Result") return <pre className="deck-extension-result">{text(binding(node.bind))}</pre>;
  if (node.type === "Error") return binding(node.bind) ? <p role="alert" className="deck-error">{text(binding(node.bind))}</p> : null;
  if (node.type === "Status") return <p role="status">{text(binding(node.bind))}</p>;
  return null;
}

function ExtensionHost({ id, available }: { id: string; available: boolean }) {
  const { t } = useTranslation("gui");
  const [view, setView] = useState<ExtensionView | null>(null);
  const [inputs, setInputs] = useState<Inputs>({});
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelPending, setCancelPending] = useState(false);
  const active = useRef<{ controller: AbortController; invocation: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    active.current?.controller.abort();
    active.current = null;
    setBusy(false);
    setCancelPending(false);
    setView(null);
    setError("");
    void request<ExtensionView>(`/${encodeURIComponent(id)}/view`, undefined, controller.signal).then((next) => {
      if (next.view.version !== 1) throw new Error(t("extensionsVersion"));
      setError("");
      setView(next); setInputs(defaults(next.view.view)); setResult(null);
    }).catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err)); });
    return () => { controller.abort(); active.current?.controller.abort(); };
  }, [id, available]);

  async function execute(action: string, bindings?: Record<string, string>) {
    if (!view || busy || !available || !view.execution_available) return;
    setError(""); setResult(null); setBusy(true); setCancelPending(false);
    const controller = new AbortController();
    const invocation = crypto.randomUUID();
    active.current = { controller, invocation };
    try {
      const params: Inputs = {};
      if (bindings) Object.entries(bindings).forEach(([key, reference]) => { params[key] = inputs[reference.slice(7)]; });
      else {
        const keys = view.actions[action]?.input_keys;
        if (!keys) throw new Error(t("extensionsBindingsRequired"));
        keys.forEach((key) => { if (Object.hasOwn(inputs, key)) params[key] = inputs[key]; });
      }
      const response = await request<Invocation>(`/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
        invocation_id: invocation, digest: view.digest, params,
      }, controller.signal);
      if (controller.signal.aborted) return;
      setResult(response.result);
      if (!response.ok) setError(response.error?.message ?? t("extensionsFailed"));
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!controller.signal.aborted) { setBusy(false); setCancelPending(false); }
      if (active.current?.invocation === invocation) active.current = null;
    }
  }

  async function cancelActive() {
    const current = active.current;
    if (!current) return;
    setCancelPending(true);
    try {
      await request(`/${encodeURIComponent(id)}/cancel/${current.invocation}`, {});
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setCancelPending(false);
    }
  }

  return <section className="deck-settings">
    <p className="deck-hint">{t("extensionsTrustedWarning")}</p>
    {view && (!available || !view.execution_available) && <p role="status">{text(view.execution_reason ?? t("extensionsUnavailable"))}</p>}
    {view ? <Renderer node={view.view.view} inputs={inputs} update={(key, value) => setInputs((previous) => ({ ...previous, [key]: value }))}
      result={result} busy={busy} enabled={available && view.execution_available} execute={(action, bindings) => void execute(action, bindings)} />
      : !error && <p role="status">{t("working")}</p>}
    {busy && <div className="deck-actions"><p role="status">{t(cancelPending ? "extensionsCancelling" : "working")}</p>
      <button disabled={cancelPending} onClick={() => void cancelActive()}>{t("extensionsCancel")}</button></div>}
    {error && <p role="alert" className="deck-error">{text(error)}</p>}
  </section>;
}

export function ExtensionMenu() {
  const { t } = useTranslation("gui");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const next = await request<Catalog>("", undefined, controller.signal);
        setCatalog(next); setError("");
        setSelected((current) => next.extensions.some((entry) => entry.id === current) ? current : null);
      } catch (err) {
        if (!controller.signal.aborted) { setCatalog(null); setSelected(null); setError(err instanceof Error ? err.message : String(err)); }
      } finally { pending = false; }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  const entry = catalog?.extensions.find((item) => item.id === selected);
  return <div className="deck-extensions">
    {error && <p role="alert" className="deck-error">{text(error)}</p>}
    {catalog?.safe_mode && <p role="status">{t("extensionsSafeMode")}</p>}
    {Boolean(catalog?.invalid_package_count) && <p role="alert">{t("extensionsInvalid")}</p>}
    {catalog?.extensions.length === 0 && <p>{t("extensionsEmpty")}</p>}
    {!catalog && !error && <p role="status">{t("working")}</p>}
    <ul className="deck-device-list" aria-label={t("extensions")}>
      {catalog?.extensions.map((item) => <li key={item.id}><button aria-pressed={selected === item.id}
        onClick={() => setSelected(selected === item.id ? null : item.id)}>{text(item.menu.label)}</button></li>)}
    </ul>
    {entry && <ExtensionHost key={entry.id} id={entry.id} available={entry.execution_available} />}
  </div>;
}
