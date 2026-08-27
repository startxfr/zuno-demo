// Wire shapes of the SSE events streamed end to end (ADR-0045) from
// components/agent-runtime/app/main.py:_sse through agent-bff and this
// frontend's own /api/chat proxy, unchanged byte-for-byte at each hop.
export interface Citation {
  source: string;
  title: string;
}

// ADR-0415: a generate_image tool result for this turn - sidecar field,
// same shape/placement convention as Citation above.
export interface ImageArtifact {
  data_base64: string;
  mime_type: string;
  alt: string;
}

export interface StartEventData {
  request_id: string;
  // ADR-0212: identifies this conversation - unchanged from ADR-0103's
  // contract, but captured by Chat.tsx for the first time here (this
  // component's own half of the resume contract).
  run_id: string;
  // ADR-0528: the server-resolved project for this run, empty outside a
  // project. Authoritative - a client-requested project_id is only a
  // request until the server has verified the caller's grant on it.
  project_id?: string;
}

export interface TokenEventData {
  delta: string;
}

export interface ToolEventData {
  name: string;
  status: "started" | "finished";
}

export interface DoneEventData {
  citations: Citation[];
  images?: ImageArtifact[];
}

export interface ErrorEventData {
  message: string;
}

export type ChatRole = "user" | "agent" | "error";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations?: Citation[];
  images?: ImageArtifact[];
  pending?: boolean;
}
