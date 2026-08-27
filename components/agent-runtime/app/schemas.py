from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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
    #
    # ADR-0527: the project this conversation belongs to. Honoured ONLY
    # when creating a brand-new conversation (run_id is None), and even
    # then only after app/main.py's agent_chat has verified the caller
    # holds a `write` grant on it - the value never reaches AgentState
    # unverified, because _initial_state no longer copies it at all.
    # On resume it is ignored entirely (a conversation's project is fixed
    # at creation) and only logged on mismatch, the same posture
    # _initial_state already applies to an informational user_sub.
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


# ADR-0527 clause 5: the project context's storage and input ceiling.
# Mirrored in app/projects.py, in _DDL's ck_projects_context_length (the
# backstop) and in web/src/shared/projects.ts (the live counter).
PROJECT_CONTEXT_MAX_CHARS = 54000

ProjectRole = Literal["read", "clone", "write", "admin"]


class ProjectGrantSpec(BaseModel):
    """ADR-0527 clause 2: one grant, targeting exactly one of a Keycloak
    subject or a business-role group. The XOR mirrors project_grants'
    own ck_project_grants_subject_xor_group - validated here so the API
    returns a 400 that names the rule, rather than surfacing a constraint
    violation as a 500. app/projects.py's assert_grants_are_valid applies
    the rules this shape cannot express (the last-admin guard, duplicate
    targets, and the agent_* entitlement-group refusal)."""

    subject: Optional[str] = Field(default=None, min_length=1)
    group_name: Optional[str] = Field(default=None, min_length=1)
    role: ProjectRole

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "ProjectGrantSpec":
        if (self.subject is None) == (self.group_name is None):
            raise ValueError("exactly one of subject or group_name must be set")
        return self


class CreateProjectRequest(BaseModel):
    # ADR-0527: POST /v1/projects body. `grants` is the full desired set;
    # app/main.py merges the creator's own admin grant into it before
    # persisting, so a project can never be created unadministrable.
    title: str = Field(min_length=1, max_length=200)
    context: str = Field(default="", max_length=PROJECT_CONTEXT_MAX_CHARS)
    classification: Literal["C1", "C2", "C3"] = "C2"
    # ADR-0528: optional. Present and verifiable => customer project;
    # absent => free project. Verified at save time under the caller's own
    # identity, never stored unverified.
    salesforce_opportunity_id: Optional[str] = Field(default=None, min_length=1)
    grants: List[ProjectGrantSpec] = Field(default_factory=list)


class SaveProjectRequest(CreateProjectRequest):
    # ADR-0527: PUT /v1/projects/{project_id} body - the whole desired
    # state at once, which is why this ADR needs one endpoint where
    # ADR-0213 needed five (the dialog stages every change and commits on
    # a single validation).
    #
    # grants=None means "the caller may not edit grants" - a `write`
    # member editing only the Description tab - and leaves them untouched.
    # A non-None value is the FULL desired set: anything absent is revoked.
    grants: Optional[List[ProjectGrantSpec]] = None
