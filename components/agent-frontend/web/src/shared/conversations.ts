import type { ProjectRole } from "./projects";

// ADR-0212/ADR-0527: thin fetch wrappers for this page's own
// conversation-management proxy routes (components/agent-frontend/internal/chat/chat.go's
// ConversationsProxyHandler), used by shared/ConversationList.tsx and
// chat/Chat.tsx. Same JSON-error-parsing shape as chat/Chat.tsx's own
// send() function.

export interface Conversation {
  run_id: string;
  title: string;
  updated_at: string;
  starred: boolean;
  // ADR-0527: the project this conversation belongs to, or null for a
  // project-less conversation private to its owner. Drives which sidebar
  // block the row lands in.
  project_id: string | null;
  // The caller's effective right on THIS conversation - their project role,
  // or write/admin when they own it. null only for a row the server could
  // not resolve. read/clone render the tab without a composer.
  role: ProjectRole | null;
}

export interface TranscriptTurn {
  role: "user" | "assistant";
  content: string;
  ts: string;
  // ADR-0415: present only on an assistant turn that generated at least
  // one image.
  images?: { data_base64: string; mime_type: string; alt: string }[];
}

async function parseOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    let detail = body;
    try {
      detail = JSON.parse(body).error ?? body;
    } catch {
      // body wasn't JSON - use it verbatim
    }
    throw new Error(detail || `request failed with status ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function listConversations(conversationsURL: string, starredOnly = false): Promise<Conversation[]> {
  const url = starredOnly ? `${conversationsURL}?starred=true` : conversationsURL;
  return parseOrThrow<Conversation[]>(await fetch(url));
}

export async function getTranscript(conversationsURL: string, runId: string): Promise<TranscriptTurn[]> {
  const url = `${conversationsURL}/${encodeURIComponent(runId)}/transcript`;
  return parseOrThrow<TranscriptTurn[]>(await fetch(url));
}

export async function renameConversation(conversationsURL: string, runId: string, title: string): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
  );
}

export async function setStar(conversationsURL: string, runId: string, starred: boolean): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/star`, {
      method: starred ? "PUT" : "DELETE",
    }),
  );
}

export async function deleteConversation(conversationsURL: string, runId: string): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}`, { method: "DELETE" }),
  );
}

// ADR-0515: persists a drag-drop reorder - runIds is the full desired
// order for this agent's conversation list.
export async function reorderConversations(conversationsURL: string, runIds: string[]): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/reorder`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_ids: runIds }),
    }),
  );
}

// ADR-0515: irreversible - unlike deleteConversation above (soft-delete/
// archive), this purges the conversation's metadata row and its
// underlying message history entirely. Callers must confirm with the
// user before calling this.
export async function hardDeleteConversation(conversationsURL: string, runId: string): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/hard-delete`, { method: "DELETE" }),
  );
}

// ADR-0527 clause 4: the clone stays in the SOURCE's project and takes a
// derived title, and the cloner owns it - so they may write to their own
// copy while remaining unable to write to the original. Returns enough to
// open the new tab without re-fetching the list.
export async function cloneConversation(
  conversationsURL: string,
  runId: string,
): Promise<{ run_id: string; title: string; project_id: string }> {
  return parseOrThrow<{ run_id: string; title: string; project_id: string }>(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/clone`, { method: "POST" }),
  );
}
