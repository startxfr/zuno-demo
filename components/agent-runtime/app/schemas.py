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


class Citation(BaseModel):
    source: str
    title: str


class ChatResponse(BaseModel):
    reply: str
    citations: List[Citation]
    # ADR-0103: pass this back as `run_id` on a later request (browser
    # disconnect, explicit "continue" action) to resume this exact
    # workflow from its last checkpoint instead of starting a new one.
    run_id: str
