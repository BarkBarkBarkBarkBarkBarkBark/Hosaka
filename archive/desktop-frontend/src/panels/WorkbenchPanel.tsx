import { useEffect, useMemo, useState } from "react";
import type { ConversationEntry } from "../chat/conversationLog";
import type { AppDefinition, AppId } from "../ui/appRegistry";

type ReadingCollection = {
  id: string;
  summary?: string;
  description?: string;
};

export type WorkbenchPanelProps = {
  apps: AppDefinition[];
  conversation: ConversationEntry[];
  onOpenApp: (appId: AppId) => void;
  onStageCommand: (command: string, autoSubmit?: boolean) => void;
};

export function WorkbenchPanel({ apps, conversation, onOpenApp, onStageCommand }: WorkbenchPanelProps) {
  const [collections, setCollections] = useState<ReadingCollection[]>([]);
  const [selected, setSelected] = useState<string>("app:terminal");

  useEffect(() => {
    fetch("/reading/collections.json")
      .then((response) => response.json())
      .then((data: ReadingCollection[]) => setCollections(Array.isArray(data) ? data : []))
      .catch(() => setCollections([]));
  }, []);

  const treeItems = useMemo(
    () => [
      ...apps.map((app) => ({ id: `app:${app.id}`, title: `${app.glyph} ${app.title}`, detail: app.description })),
      ...collections.map((collection) => ({
        id: `doc:${collection.id}`,
        title: collection.id,
        detail: collection.summary ?? collection.description ?? "reading collection",
      })),
    ],
    [apps, collections],
  );

  const selectedItem = treeItems.find((item) => item.id === selected) ?? treeItems[0] ?? null;
  const visibleConversation = conversation.filter((entry) => entry.visibility === "visible").slice(-10).reverse();

  return (
    <div className="workbench-panel">
      <div className="panel-header">
        <h2>
          <span className="panel-glyph">▤</span> workbench
        </h2>
        <p className="panel-sub">
          lightweight faux-ide: tree on the left, preview in the middle, shared chat on the right, command deck below.
        </p>
      </div>

      <div className="workbench-layout">
        <aside className="workbench-tree">
          <div className="workbench-section-title">tree</div>
          {treeItems.map((item) => (
            <button
              key={item.id}
              className={`workbench-tree-item ${selected === item.id ? "is-active" : ""}`}
              onClick={() => setSelected(item.id)}
            >
              <strong>{item.title}</strong>
              <span>{item.detail}</span>
            </button>
          ))}
        </aside>

        <section className="workbench-preview">
          <div className="workbench-section-title">preview</div>
          {selectedItem ? (
            <div className="workbench-preview-card">
              <strong>{selectedItem.title}</strong>
              <p>{selectedItem.detail}</p>
              {selectedItem.id.startsWith("app:") ? (
                <div className="workbench-actions">
                  <button
                    className="btn btn-primary"
                    onClick={() => onOpenApp(selectedItem.id.replace("app:", "") as AppId)}
                  >
                    launch app
                  </button>
                  <button
                    className="btn btn-ghost"
                    onClick={() => onStageCommand(`/launch ${selectedItem.id.replace("app:", "")}`)}
                  >
                    stage /launch
                  </button>
                </div>
              ) : (
                <div className="workbench-actions">
                  <button
                    className="btn btn-primary"
                    onClick={() => onStageCommand(`/read ${selectedItem.id.replace("doc:", "")}`, true)}
                  >
                    open doc
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="dim">no preview available.</div>
          )}
        </section>

        <aside className="workbench-chat">
          <div className="workbench-section-title">shared chat</div>
          <div className="workbench-chat-log">
            {visibleConversation.length === 0 && <div className="dim">voice + text history will appear here.</div>}
            {visibleConversation.map((entry) => (
              <div key={entry.id} className={`workbench-chat-entry role-${entry.role}`}>
                <span>{entry.source}</span>
                <strong>{entry.role}</strong>
                <p>{entry.text}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="workbench-command-deck">
        <div className="workbench-section-title">command deck</div>
        <div className="workbench-command-buttons">
          <button className="btn btn-ghost" onClick={() => onStageCommand("/launch terminal")}>/launch terminal</button>
          <button className="btn btn-ghost" onClick={() => onStageCommand("/launch voice")}>/launch voice</button>
          <button className="btn btn-ghost" onClick={() => onStageCommand("/launch web")}>/launch web</button>
          <button className="btn btn-ghost" onClick={() => onStageCommand("/agent status")}>/agent status</button>
        </div>
      </div>
    </div>
  );
}
