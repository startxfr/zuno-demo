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

// ADR-0213: role-based conversation sharing.
export type MembershipRole = "reader" | "actor" | "cloner";

export interface Member {
  subject: string;
  role: MembershipRole;
  granted_by: string;
  created_at: string;
}

export interface Colleague {
  sub: string;
  displayName: string;
  // Ineligible candidates are still included so the caller can render
  // them greyed out rather than hide them, per the ADR's explicit
  // product requirement.
  eligible: boolean;
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

// ADR-0213: role-based conversation sharing.

export async function listMembers(conversationsURL: string, runId: string): Promise<Member[]> {
  return parseOrThrow<Member[]>(await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/members`));
}

export async function grantMembership(
  conversationsURL: string,
  runId: string,
  subject: string,
  role: MembershipRole,
): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/members/${encodeURIComponent(subject)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),
  );
}

export async function revokeMembership(conversationsURL: string, runId: string, subject: string): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/members/${encodeURIComponent(subject)}`, {
      method: "DELETE",
    }),
  );
}

export async function transferOwnership(conversationsURL: string, runId: string, newOwnerSub: string): Promise<void> {
  await parseOrThrow(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/owner`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_owner_sub: newOwnerSub }),
    }),
  );
}

// Returns the new, independently-owned conversation's run_id.
export async function cloneConversation(conversationsURL: string, runId: string): Promise<string> {
  const result = await parseOrThrow<{ run_id: string }>(
    await fetch(`${conversationsURL}/${encodeURIComponent(runId)}/clone`, { method: "POST" }),
  );
  return result.run_id;
}

// Debounced by the caller (ShareDialog.tsx) - this is a plain type-ahead
// wrapper, no debounce logic of its own.
export async function getColleagues(colleaguesURL: string, query: string): Promise<Colleague[]> {
  const url = query ? `${colleaguesURL}?q=${encodeURIComponent(query)}` : colleaguesURL;
  return parseOrThrow<Colleague[]>(await fetch(url));
}
