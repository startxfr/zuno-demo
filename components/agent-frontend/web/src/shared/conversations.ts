// ADR-0212: thin fetch wrappers for this page's own conversation-management
// proxy routes (components/agent-frontend/internal/chat/chat.go's
// ConversationsProxyHandler), used by shared/ConversationList.tsx and
// chat/Chat.tsx. Same JSON-error-parsing shape as chat/Chat.tsx's own
// send() function.

export interface Conversation {
  run_id: string;
  title: string;
  updated_at: string;
  starred: boolean;
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
