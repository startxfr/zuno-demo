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

// ADR-0550 (WP-135): the real, server-side model-routing decision for
// this turn - see components/agent-runtime/app/schemas.py's
// RoutingMetadata (the source of truth) and components/agent-bff's own
// mirrored Go struct. Every field degrades to an empty/false placeholder
// rather than being omitted when the underlying ai-gateway fetch fails -
// this is a read-only, explainability-only projection, never re-derived
// or re-implemented client-side.
export interface RoutingMetadata {
  agent: string;
  task: string;
  project_id: string;
  project_classification: string;
  effective_classification: string;
  selected_model: string;
  selected_provider: string;
  execution_location: "local" | "external" | "unknown";
  fallback_used: boolean;
  fallback_from?: string | null;
  local_only_required: boolean;
  routing_reason: string;
}

export interface DoneEventData {
  citations: Citation[];
  images?: ImageArtifact[];
  routing?: RoutingMetadata;
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
  routing?: RoutingMetadata;
  pending?: boolean;
}
