import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "../i18n";

type Value = string | number | boolean;
type Inputs = Record<string, Value>;
type AppPage = { label: string; view: Component; load?: { action: string; params: Record<string, string> } };
type Component =
  | { type: "Stack"; children: Component[] }
  | { type: "Navigation"; pages: AppPage[] }
  | { type: "Details"; label: string; children: Component[] }
  | { type: "Heading" | "Text"; text: string }
  | { type: "Button"; label: string; action: string; params?: Record<string, string> }
  | { type: "TextInput"; id: string; label: string; default?: string }
  | { type: "FileInput"; id: string; filename_id: string; label: string }
  | { type: "Files"; bind: string }
  | { type: "LookupInput"; id: string; selection_id: string; label: string; action: string;
      query_param: string; label_field: string; value_field: string; max_length: number;
      description_field?: string; params?: Record<string, string> }
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
  if (node.type === "Stack" || node.type === "Details") node.children.forEach((child) => defaults(child, inputs));
  if (node.type === "Navigation") node.pages.forEach((page) => defaults(page.view, inputs));
  if (node.type === "TextInput") inputs[node.id] = node.default ?? "";
  if (node.type === "LookupInput") { inputs[node.id] = ""; inputs[node.selection_id] = ""; }
  if (node.type === "FileInput") { inputs[node.id] = ""; inputs[node.filename_id] = ""; }
  if (node.type === "NumberInput") inputs[node.id] = node.default ?? 0;
  if (node.type === "Checkbox") inputs[node.id] = node.default ?? false;
  if (node.type === "Select") inputs[node.id] = node.default ?? node.options[0];
  return inputs;
}

type RendererProps = {
  node: Component; inputs: Inputs; update: (id: string, value: Value) => void;
  result: Record<string, unknown> | null; busy: boolean; enabled: boolean;
  execute: (action: string, bindings?: Record<string, string>) => void;
  lookup: (action: string, params: Inputs, signal: AbortSignal) => Promise<Record<string, unknown>>;
  navigate: () => void;
  upload: (file: File) => Promise<{ id: string; filename: string }>;
  fileUrl: (name: string) => string;
};

function FileInput({ node, update, upload, busy, enabled }: {
  node: Extract<Component, {type: "FileInput"}>;
} & Pick<RendererProps, "update" | "upload" | "busy" | "enabled">) {
  const [error, setError] = useState("");
  return <div><label>{text(node.label)}<input type="file" accept=".jpg,.jpeg,.png,.webp,.pdf"
    disabled={busy || !enabled} onChange={(event) => {
      const file = event.target.files?.[0];
      update(node.id, ""); update(node.filename_id, ""); setError("");
      if (!file) return;
      void upload(file).then((result) => {
        update(node.id, result.id); update(node.filename_id, result.filename);
      }).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    }} /></label>{error && <p role="alert" className="deck-error">{text(error)}</p>}</div>;
}

function LookupInput({ node, inputs, update, lookup, busy, enabled }: {
  node: Extract<Component, { type: "LookupInput" }>;
} & Pick<RendererProps, "inputs" | "update" | "lookup" | "busy" | "enabled">) {
  const { t } = useTranslation("gui");
  const input = useRef<HTMLInputElement>(null);
  const [matches, setMatches] = useState<{ label: string; value: string; description: string }[]>([]);
  const [selectedDescription, setSelectedDescription] = useState("");
  const [focused, setFocused] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [truncated, setTruncated] = useState(false);
  const value = String(inputs[node.id] ?? "");
  const selection = String(inputs[node.selection_id] ?? "");
  const listId = `extension-lookup-${node.id}`;
  const invalidMessage = t("extensionsLookupInvalid");
  const scope = JSON.stringify(Object.fromEntries(
    Object.entries(node.params ?? {}).map(([key, binding]) => [key, inputs[binding.slice(7)]]),
  ));
  const previousScope = useRef(scope);

  useEffect(() => {
    const controller = new AbortController();
    setMatches([]); setHighlighted(-1); setError(""); setLoading(false); setTruncated(false);
    if (previousScope.current !== scope) {
      previousScope.current = scope; update(node.selection_id, ""); setSelectedDescription("");
    }
    if (!focused || !value.trim() || selection || busy || !enabled) { setOpen(false); return; }
    const timer = window.setTimeout(() => {
      setLoading(true);
      const context: Inputs = JSON.parse(scope);
      void lookup(node.action, { ...context, [node.query_param]: value }, controller.signal).then((result) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(result.rows)) throw new Error(invalidMessage);
        const rows = result.rows.map((row: unknown) => {
          if (typeof row !== "object" || row === null) throw new Error(invalidMessage);
          const label: unknown = Reflect.get(row, node.label_field);
          const id: unknown = Reflect.get(row, node.value_field);
          const description: unknown = node.description_field ? Reflect.get(row, node.description_field) : "";
          if (typeof label !== "string" || !label || label.length > node.max_length
            || typeof id !== "string" || !id || id.length > 2048
            || typeof description !== "string" || description.length > 2048) throw new Error(invalidMessage);
          return { label, value: id, description };
        });
        if (new Set(rows.map((row) => row.value)).size !== rows.length) throw new Error(invalidMessage);
        setMatches(rows.slice(0, 8)); setTruncated(rows.length > 8);
        setOpen(input.current === document.activeElement);
      }).catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err)); setOpen(false);
        }
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [value, selection, focused, scope, busy, enabled, lookup, node.action, node.query_param, node.label_field,
    node.value_field, node.description_field, node.max_length, node.selection_id, invalidMessage]);

  function select(index: number) {
    const match = matches[index];
    update(node.id, match.label); update(node.selection_id, match.value);
    setSelectedDescription(match.description);
    setOpen(false); setHighlighted(-1);
    input.current?.focus();
  }

  return <div className="deck-extension-lookup">
    <label>{text(node.label)}<input ref={input} role="combobox" aria-autocomplete="list"
      aria-expanded={open} aria-controls={listId} autoComplete="off" maxLength={node.max_length}
      aria-activedescendant={open && highlighted >= 0 ? `${listId}-${highlighted}` : undefined}
      disabled={busy || !enabled} value={value} onChange={(event) => {
        update(node.id, event.target.value); update(node.selection_id, "");
        setMatches([]); setHighlighted(-1); setOpen(false); setSelectedDescription("");
      }} onFocus={() => {
        setFocused(true);
        if (selection) { update(node.selection_id, ""); setSelectedDescription(""); }
        if (matches.length) setOpen(true);
      }} onBlur={() => { setFocused(false); setOpen(false); }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault(); event.stopPropagation(); setOpen(false);
        } else if ((event.key === "ArrowDown" || event.key === "ArrowUp") && matches.length) {
          event.preventDefault(); setOpen(true);
          setHighlighted((current) => (current + (event.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length);
        } else if (event.key === "Enter" && open && highlighted >= 0) {
          event.preventDefault(); select(highlighted);
        }
      }} /></label>
    {selectedDescription && <p className="deck-hint">{text(selectedDescription)}</p>}
    {loading && <p className="deck-hint" role="status">{t("extensionsLookupLoading")}</p>}
    {error && <p className="deck-error" role="alert">{text(error)}</p>}
    {open && <div className="deck-extension-suggestions">
      <ul id={listId} role="listbox" aria-label={text(node.label)}>
        {matches.map((match, index) => <li key={match.value} id={`${listId}-${index}`} role="option"
          aria-selected={highlighted === index} onMouseDown={(event) => event.preventDefault()}
          onClick={() => select(index)} onMouseMove={() => setHighlighted(index)}>
          {text(match.label)}
          {match.description && <small>{text(match.description)}</small>}
          {!node.description_field && matches.some((other, otherIndex) => otherIndex !== index && other.label === match.label)
            && <small>{text(match.value)}</small>}
        </li>)}
      </ul>
      {matches.length === 0 && <p>{t("extensionsLookupNoMatches")}</p>}
      {truncated && <p>{t("extensionsLookupTruncated")}</p>}
    </div>}
  </div>;
}

function Navigation({ pages, ...props }: Omit<RendererProps, "node"> & {
  pages: AppPage[];
}) {
  const { t } = useTranslation("gui");
  const [selected, setSelected] = useState(0);
  const menu = useRef<HTMLDetailsElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const previous = useRef(selected);
  const loaded = useRef<number | null>(null);
  const execute = useRef(props.execute);
  execute.current = props.execute;
  useEffect(() => {
    if (loaded.current === selected) return;
    loaded.current = selected;
    const load = pages[selected].load;
    if (load) execute.current(load.action, load.params);
  }, [selected, pages]);
  useEffect(() => {
    if (previous.current !== selected) {
      panel.current?.focus();
      previous.current = selected;
    }
  }, [selected]);
  return <div className="deck-extension-navigation">
    <header>
      <h2 id="extension-page-title">{text(pages[selected].label)}</h2>
      <details ref={menu} data-extension-navigation>
        <summary>{t("extensionsAppMenu")}</summary>
        <nav aria-label={t("extensionsAppMenu")}>
          {pages.map((page, index) => <button key={page.label} disabled={props.busy}
            aria-current={index === selected ? "page" : undefined} onClick={() => {
              if (index !== selected) {
                props.navigate();
                setSelected(index);
              }
              if (menu.current) menu.current.open = false;
              if (index === selected) menu.current?.querySelector("summary")?.focus();
            }}>{text(page.label)}</button>)}
        </nav>
      </details>
    </header>
    <div className="deck-extension-page" ref={panel} tabIndex={-1} aria-labelledby="extension-page-title">
      <Renderer key={selected} {...props} node={pages[selected].view} />
    </div>
  </div>;
}

function Renderer({ node, inputs, update, result, busy, enabled, execute, lookup, navigate, upload, fileUrl }: RendererProps) {
  const { t } = useTranslation("gui");
  const child = (component: Component, index: number) => <Renderer key={index} node={component}
    inputs={inputs} update={update} result={result} busy={busy} enabled={enabled} execute={execute} lookup={lookup}
    navigate={navigate} upload={upload} fileUrl={fileUrl} />;
  function binding(reference: string): unknown {
    const [scope, field] = reference.split(".");
    return scope === "params" ? (Object.hasOwn(inputs, field) ? inputs[field] : undefined)
      : result && Object.hasOwn(result, field) ? result[field] : undefined;
  }
  if (node.type === "Navigation") return <Navigation pages={node.pages} inputs={inputs} update={update}
    result={result} busy={busy} enabled={enabled} execute={execute} lookup={lookup} navigate={navigate} upload={upload} fileUrl={fileUrl} />;
  if (node.type === "Stack") return <div className="deck-extension-stack">{node.children.map(child)}</div>;
  if (node.type === "Details") return <details className="deck-extension-details">
    <summary>{text(node.label)}</summary><div className="deck-extension-stack">{node.children.map(child)}</div>
  </details>;
  if (node.type === "Heading") return <h2>{text(node.text)}</h2>;
  if (node.type === "Text") return <p>{text(node.text)}</p>;
  if (node.type === "FileInput") return <FileInput node={node} update={update} upload={upload} busy={busy} enabled={enabled} />;
  if (node.type === "Files") {
    const files = binding(node.bind);
    if (files === undefined || files === null) return null;
    if (!Array.isArray(files)) return <p role="alert">{t("extensionsFilesInvalid")}</p>;
    if (files.some((file: unknown) => typeof file !== "object" || file === null
      || typeof Reflect.get(file, "name") !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/.test(Reflect.get(file, "name"))
      || typeof Reflect.get(file, "label") !== "string")) return <p role="alert">{t("extensionsFilesInvalid")}</p>;
    return <ul>{files.map((file: {name: string; label: string}) =>
      <li key={file.name}><a href={fileUrl(file.name)} download>{text(file.label)}</a></li>)}</ul>;
  }
  if (node.type === "LookupInput") return <LookupInput node={node} inputs={inputs} update={update}
    lookup={lookup} busy={busy} enabled={enabled} />;
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
  const active = useRef<{ controller: AbortController; invocation: string; started: boolean } | null>(null);
  const requests = useRef(new Set<AbortController>());
  const queue = useRef<Promise<void>>(Promise.resolve());
  const unavailableMessage = t("extensionsUnavailable");
  const lookupBusyMessage = t("extensionsLookupBusy");
  const failedMessage = t("extensionsFailed");

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
    return () => {
      controller.abort(); active.current?.controller.abort();
      requests.current.forEach((request) => request.abort());
    };
  }, [id, available]);

  const invoke = useCallback((
    action: string, params: Inputs, invocation: string, controller: AbortController,
    current: () => boolean = () => true, onStart?: () => void,
  ): Promise<Invocation> => {
    if (requests.current.size >= 8) return Promise.reject(new Error(lookupBusyMessage));
    requests.current.add(controller);
    const perform = async () => {
      try {
        if (controller.signal.aborted || !current()) throw new DOMException("Cancelled", "AbortError");
        if (!view || !available || !view.execution_available) throw new Error(unavailableMessage);
        onStart?.();
        return await request<Invocation>(`/${encodeURIComponent(id)}/actions/${encodeURIComponent(action)}`, {
          invocation_id: invocation, digest: view.digest, params,
        }, controller.signal);
      } finally { requests.current.delete(controller); }
    };
    const result = queue.current.then(perform);
    // Every caller receives its own rejection; only the scheduling tail is settled.
    queue.current = result.then(() => {}, () => {});
    return result;
  }, [id, view, available, unavailableMessage, lookupBusyMessage]);

  const lookup = useCallback(async (action: string, params: Inputs, signal: AbortSignal) => {
    const report = await invoke(action, params, crypto.randomUUID(), new AbortController(), () => !signal.aborted);
    if (!report.ok || !report.result) throw new Error(report.error?.message ?? failedMessage);
    return report.result;
  }, [invoke, failedMessage]);

  async function execute(action: string, bindings?: Record<string, string>) {
    if (!view || busy || !available || !view.execution_available) return;
    setError(""); setResult(null); setBusy(true); setCancelPending(false);
    const controller = new AbortController();
    const invocation = crypto.randomUUID();
    active.current = { controller, invocation, started: false };
    try {
      const params: Inputs = {};
      if (bindings) Object.entries(bindings).forEach(([key, reference]) => { params[key] = inputs[reference.slice(7)]; });
      else {
        const keys = view.actions[action]?.input_keys;
        if (!keys) throw new Error(t("extensionsBindingsRequired"));
        keys.forEach((key) => { if (Object.hasOwn(inputs, key)) params[key] = inputs[key]; });
      }
      const response = await invoke(action, params, invocation, controller, undefined, () => {
        if (active.current?.invocation === invocation) active.current.started = true;
      });
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
    if (!current.started) {
      current.controller.abort(); active.current = null;
      setBusy(false); setCancelPending(false); setError(t("extensionsCancelled"));
      return;
    }

    setCancelPending(true);
    try {
      await request(`/${encodeURIComponent(id)}/cancel/${current.invocation}`, {});
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setCancelPending(false);
    }
  }

  async function upload(file: File): Promise<{id: string; filename: string}> {
    if (!view || !available || !view.execution_available || busy) throw new Error(unavailableMessage);
    if (!file.size || file.size > 10485760) throw new Error(t("extensionsFileSize"));
    setBusy(true);
    const controller = new AbortController();
    requests.current.add(controller);
    active.current = {controller, invocation: "", started: false};
    try {
      const response = await fetch(`/api/v1/extensions/${encodeURIComponent(id)}/files`, {
        method: "POST", body: file, signal: controller.signal, headers: {
          "X-Extension-Digest": view.digest, "X-Extension-Filename": encodeURIComponent(file.name),
          "Content-Type": "application/octet-stream",
        },
      });
      const result: {id: string; filename: string; detail?: string} = await response.json();
      if (!response.ok) throw new Error(result.detail ?? `HTTP ${response.status}`);
      if (typeof result.id !== "string" || !/^[a-f0-9]{32}$/.test(result.id) || typeof result.filename !== "string") {
        throw new Error(t("extensionsFilesInvalid"));
      }
      return result;
    } finally {
      requests.current.delete(controller);
      if (active.current?.controller === controller) active.current = null;
      setBusy(false);
    }
  }

  return <section className="deck-settings">
    {view?.view.view.type === "Navigation"
      ? <details className="deck-extension-details deck-hint"><summary>{t("extensionsRuntimeInfo")}</summary>
        <p>{t("extensionsTrustedWarning")}</p></details>
      : <p className="deck-hint">{t("extensionsTrustedWarning")}</p>}
    {view && (!available || !view.execution_available) && <p role="status">{text(view.execution_reason ?? t("extensionsUnavailable"))}</p>}
    {view ? <Renderer node={view.view.view} inputs={inputs} update={(key, value) => setInputs((previous) => ({ ...previous, [key]: value }))}
      result={result} busy={busy} enabled={available && view.execution_available} execute={(action, bindings) => void execute(action, bindings)}
      lookup={lookup} navigate={() => { setResult(null); setError(""); }} upload={upload}
      fileUrl={(name) => `/api/v1/extensions/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`} />
      : !error && <p role="status">{t("working")}</p>}
    {busy && <div className="deck-actions"><p role="status">{t(cancelPending ? "extensionsCancelling" : "working")}</p>
      <button disabled={cancelPending} onClick={() => void cancelActive()}>{t("extensionsCancel")}</button></div>}
    {error && <p role="alert" className="deck-error">{text(error)}</p>}
  </section>;
}

export function ExtensionMenu({ onAppChange }: { onAppChange: (name: string | null) => void }) {
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
  useEffect(() => {
    onAppChange(entry?.name ?? null);
    return () => onAppChange(null);
  }, [entry?.name, onAppChange]);
  return <div className="deck-extensions">
    {error && <p role="alert" className="deck-error">{text(error)}</p>}
    {catalog?.safe_mode && <p role="status">{t("extensionsSafeMode")}</p>}
    {Boolean(catalog?.invalid_package_count) && <p role="alert">{t("extensionsInvalid")}</p>}
    {catalog?.extensions.length === 0 && <p>{t("extensionsEmpty")}</p>}
    {!catalog && !error && <p role="status">{t("working")}</p>}
    {!entry && <ul className="deck-device-list" aria-label={t("extensions")}>
      {catalog?.extensions.map((item) => <li key={item.id}><button aria-pressed={selected === item.id}
        onClick={() => setSelected(selected === item.id ? null : item.id)}>{text(item.menu.label)}</button></li>)}
    </ul>}
    {entry && <ExtensionHost key={entry.id} id={entry.id} available={entry.execution_available} />}
  </div>;
}
