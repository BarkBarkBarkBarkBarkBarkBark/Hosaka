import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type Loop = {
  id: string;
  text: string;
  closed: boolean;
  ts: number;
};

const STORAGE_KEY = "hosaka.todo.v1";

function loadLoops(): Loop[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Loop[];
  } catch {
    return [];
  }
}

function saveLoops(loops: Loop[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(loops));
}

export function TodoPanel() {
  const { t } = useTranslation("ui");
  const [loops, setLoops] = useState<Loop[]>(loadLoops);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    const onAdd = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (text) addLoop(text);
    };
    window.addEventListener("hosaka:todo-add", onAdd as EventListener);
    return () =>
      window.removeEventListener("hosaka:todo-add", onAdd as EventListener);
  }, [loops]);

  const persist = (next: Loop[]) => {
    setLoops(next);
    saveLoops(next);
  };

  const addLoop = (text: string) => {
    const next: Loop = {
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      text,
      closed: false,
      ts: Date.now(),
    };
    persist([next, ...loops]);
  };

  const toggle = (id: string) => {
    persist(
      loops.map((l) => (l.id === id ? { ...l, closed: !l.closed } : l)),
    );
  };

  const remove = (id: string) => {
    persist(loops.filter((l) => l.id !== id));
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
