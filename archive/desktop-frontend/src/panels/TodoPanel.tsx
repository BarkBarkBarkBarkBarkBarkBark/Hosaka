import { useEffect, useState } from "react";
import { useTranslation } from "../i18n";
import { useSyncedDoc } from "../sync/useSyncedDoc";

type Loop = {
  id: string;
  text: string;
  closed: boolean;
  ts: number;
};

type TodoDoc = {
  items: Loop[];
};

// Stable reference — passing a fresh object literal to useSyncedDoc on
// every render would defeat its internal caching.
const INITIAL: TodoDoc = { items: [] };

export function TodoPanel() {
  const { t } = useTranslation("ui");
  const [doc, update] = useSyncedDoc<TodoDoc>("todo", INITIAL);
  const loops = Array.isArray(doc.items) ? doc.items : [];
  const [draft, setDraft] = useState("");

  const addLoop = (text: string) => {
    const loop: Loop = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      text,
      closed: false,
      ts: Date.now(),
    };
    update((d) => {
      if (!Array.isArray(d.items)) d.items = [];
      d.items.unshift(loop);
    });
  };

  useEffect(() => {
    const onAdd = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (text) addLoop(text);
    };
    window.addEventListener("hosaka:todo-add", onAdd as EventListener);
    return () =>
      window.removeEventListener("hosaka:todo-add", onAdd as EventListener);
    // addLoop has a stable-by-closure ref; we intentionally leave deps
    // empty so the listener isn't thrashed on every keystroke in draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (id: string) => {
    update((d) => {
      if (!Array.isArray(d.items)) return;
      const i = d.items.findIndex((l) => l.id === id);
      if (i >= 0) d.items[i].closed = !d.items[i].closed;
    });
  };

  const remove = (id: string) => {
    update((d) => {
      if (!Array.isArray(d.items)) return;
      const i = d.items.findIndex((l) => l.id === id);
      if (i >= 0) d.items.splice(i, 1);
    });
  };

  const submit = () => {
    const text = draft.trim();
    if (!text) return;
    addLoop(text);
    setDraft("");
  };

  const open = loops.filter((l) => !l.closed);
  const closed = loops.filter((l) => l.closed);

  return (
    <div className="todo-wrap">
      <header className="panel-header">
        <h2>
          <span className="panel-glyph">▣</span> {t("todo.heading")}
        </h2>
        <p className="panel-sub">
          {t("todo.sub")}
        </p>
      </header>

      <div className="todo-compose">
        <input
          type="text"
          placeholder={t("todo.placeholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          spellCheck={false}
        />
        <button className="btn" onClick={submit} disabled={!draft.trim()}>
          {t("todo.addBtn")}
        </button>
      </div>

      <div className="todo-list">
        {open.length === 0 && closed.length === 0 && (
          <p className="todo-empty" dangerouslySetInnerHTML={{ __html: t("todo.empty") }} />
        )}
        {open.map((l) => (
          <div key={l.id} className="todo-item">
            <button
              className="todo-check"
              onClick={() => toggle(l.id)}
              aria-label={t("todo.closeLoop")}
            >
              ○
            </button>
            <span className="todo-text">{l.text}</span>
            <button
              className="todo-remove btn btn-ghost"
              onClick={() => remove(l.id)}
              aria-label={t("todo.delete")}
            >
              ×
            </button>
          </div>
        ))}
        {closed.length > 0 && (
          <>
            <div className="todo-section-label">{t("todo.closedSection")}</div>
            {closed.map((l) => (
              <div key={l.id} className="todo-item todo-closed">
                <button
                  className="todo-check"
                  onClick={() => toggle(l.id)}
                  aria-label={t("todo.reopenLoop")}
                >
                  ●
                </button>
                <span className="todo-text">{l.text}</span>
                <button
                  className="todo-remove btn btn-ghost"
                  onClick={() => remove(l.id)}
                  aria-label={t("todo.delete")}
                >
                  ×
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
