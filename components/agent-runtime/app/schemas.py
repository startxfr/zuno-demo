from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    # Informational/correlation only (ADR-0033) - never an authorization
    # input. The authoritative subject always comes from the validated
    # bearer token (see app/main.py:_initial_state), regardless of this
    # field's value.
    user_sub: str = Field(min_length=1)
    message: str = Field(min_length=1)
    # ADR-0103: identifies the LangGraph checkpoint thread to resume. Omit
    # to start a new run (a fresh run_id is minted and returned in the
    # response); supply a prior response's run_id to resume that workflow
    # from its last checkpoint after a browser disconnect or a runtime
    # restart. Resuming with a token belonging to a different subject than
    # the one the run was started under is refused (see app/main.py).
    run_id: Optional[str] = Field(default=None, min_length=1)
    # ADR-0209: scopes this turn to a project's durable, cross-session,
    # cross-agent memory (knowledge.project). Optional/omitted - no
    # project_id means no project memory is read or written this turn.
    # Forwarded from components/agent-bff's own optional ChatRequest.
    # project_id field, following the same identity-propagation pattern
    # ADR-0032/0033 already use.
    project_id: Optional[str] = Field(default=None, min_length=1)


class Citation(BaseModel):
    source: str
    title: str


class ImageArtifact(BaseModel):
    """ADR-0415: a generate_image tool result for this turn. Sidecar
    field, mirroring Citation above - never folded into `reply` itself."""

    data_base64: str
    mime_type: str
    alt: str


class ChatResponse(BaseModel):
    reply: str
    citations: List[Citation]
    # ADR-0415: empty unless this turn's agent/task is entitled to
    # generate_image and the model chose to call it.
    images: List[ImageArtifact] = Field(default_factory=list)
    # ADR-0103: pass this back as `run_id` on a later request (browser
    # disconnect, explicit "continue" action) to resume this exact
    # workflow from its last checkpoint instead of starting a new one.
    run_id: str
    # ADR-0205/WP-24: "indexed" | "live" | "both" | "none" - whether this
    # answer's context came from indexed retrieval, a live capability
    # call, both, or neither. See app/graph/nodes.py:_compute_source_mode.
    source_mode: str = "indexed"


class RenameConversationRequest(BaseModel):
    # ADR-0212: PATCH /v1/agents/{agent}/runs/{run_id} body.
    title: str = Field(min_length=1, max_length=200)


class ReorderConversationsRequest(BaseModel):
    # ADR-0515: PUT /v1/agents/{agent}/conversations/reorder body - the
    # caller's full desired run_id order for this agent (as returned by
    # GET .../conversations); each entry's index becomes its sort_order.
    run_ids: List[str] = Field(min_length=1)
