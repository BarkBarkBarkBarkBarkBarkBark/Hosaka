import { useSyncedDoc } from "../sync/useSyncedDoc";
import { getStore } from "../sync/store";
import type { AppId } from "../ui/appRegistry";

export type ConversationRole = "user" | "assistant" | "system" | "tool";
export type ConversationSource = "shell" | "voice" | "agent" | "ui";
export type ConversationChannel = "text" | "voice" | "system";
export type ConversationVisibility = "visible" | "hidden";

export type ConversationEntry = {
  id: string;
  at: number;
  role: ConversationRole;
  source: ConversationSource;
  channel: ConversationChannel;
  text: string;
  visibility: ConversationVisibility;
  appId?: AppId;
  meta?: Record<string, string | number | boolean | null>;
};

export type ConversationDoc = {
  entries: ConversationEntry[];
};

const MAX_ENTRIES = 400;

export const INITIAL_CONVERSATION_DOC: ConversationDoc = {
  entries: [],
};

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useConversationLog(): [ConversationDoc, (entry: Omit<ConversationEntry, "id" | "at"> & Partial<Pick<ConversationEntry, "id" | "at">>) => void] {
  const [doc] = useSyncedDoc<ConversationDoc>("conversation", INITIAL_CONVERSATION_DOC);
  return [doc, appendConversationEntry];
}

export function appendConversationEntry(
  input: Omit<ConversationEntry, "id" | "at"> & Partial<Pick<ConversationEntry, "id" | "at">>,
): void {
  const text = input.text.trim();
  if (!text) return;
  getStore().update<ConversationDoc>("conversation", INITIAL_CONVERSATION_DOC, (doc) => {
    if (!Array.isArray(doc.entries)) doc.entries = [];
    // Automerge rejects `undefined` values (it throws "Cannot assign undefined
    // value at /entries/N/meta"), so only attach optional fields when they're
    // actually present rather than writing `undefined`.
    const entry: ConversationEntry = {
      id: input.id ?? makeId(),
      at: input.at ?? Date.now(),
      role: input.role,
      source: input.source,
      channel: input.channel,
      text,
      visibility: input.visibility,
    };
    if (input.appId !== undefined) entry.appId = input.appId;
    if (input.meta !== undefined) entry.meta = input.meta;
    doc.entries.push(entry);
    if (doc.entries.length > MAX_ENTRIES) {
      doc.entries.splice(0, doc.entries.length - MAX_ENTRIES);
    }
  });
}

export function clearConversationLog(): void {
  getStore().update<ConversationDoc>("conversation", INITIAL_CONVERSATION_DOC, (doc) => {
    doc.entries = [];
  });
}
