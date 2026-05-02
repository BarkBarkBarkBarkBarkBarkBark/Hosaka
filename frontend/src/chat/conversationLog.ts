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
    doc.entries.push({
      id: input.id ?? makeId(),
      at: input.at ?? Date.now(),
      role: input.role,
      source: input.source,
      channel: input.channel,
      text,
      visibility: input.visibility,
      appId: input.appId,
      meta: input.meta,
    });
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
