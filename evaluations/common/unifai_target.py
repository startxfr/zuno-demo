"""UnifAI target for the agent evaluations (WP-154, ADR-0573; shared by every
agent since WP-155 wave 0).

One transport, parametrised by agent name: `UnifaiTarget(password, agent=...)`.
`evaluations/tekos/unifai_target.py` re-exports this module so the original
import path keeps working.

`run_scenarios.py --target unifai` swaps the transport of the chat scenarios:
instead of agent-runtime's `/v1/agents/<agent>/chat` or the BFF, a persona
signs in to the UnifAI UI through realm `zuno` (the real browser OIDC flow:
identity service -> Keycloak form -> session cookie) and drives MAS through the
UI's own nginx path, exactly as a browser does:

    POST /api2/sessions/user.session.create    {blueprintId, metadata}
    POST /api2/sessions/user.session.execute   {sessionId, inputs, stream}
    GET  /api2/blueprints/available.blueprints.summary.get

The scenarios file is not forked: the same `scenarios.yaml` entries are served
by this module's handlers, so the pass rates are comparable with agent-runtime's.

Environment: UNIFAI_URL (the UI route), DEMO_PERSONA_PASSWORD (same as the
agent-runtime target), optional UNIFAI_WORKFLOW (workflow name; default is the
agent name, the operator's name for an OKF bundle's primary task) and
UNIFAI_TEAM_ID (the team workspace that owns the agent's workflows; a persona
only sees them by selecting that workspace, ``teamId`` on every request).
UNIFAI_TEAM_NAME (WP-156) names that workspace instead of its id: the team id
is resolved at sign-in from the identity service's ``teams.list`` (the
operator recreates group-bound teams as ``agent-<name>`` with new ids, so an
in-cluster Job cannot hard-code the id).

Each turn's routing decision (WP-148: the ai-gateway's provider, model,
classification and fallback, attached by the LLM element to the assistant
message as ``metadata.llm_response.routing``) is exposed as
``UnifaiRun.raw["routing"]``; ``routing_of()`` reads it from a final state.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

import httpx

UNIFAI_URL = os.getenv("UNIFAI_URL", "https://unifai-ui-zuno-unifai.apps.mycluster.example.com")
# The cluster's internal CA is not trusted by a workstation (same reason the
# other harnesses use `curl -k`); set UNIFAI_VERIFY_TLS=1 to verify.
VERIFY_TLS = os.getenv("UNIFAI_VERIFY_TLS", "0") == "1"

_LOGIN_FORM_RE = re.compile(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"')


# UnifAI reports a tool by its capability id; scenarios name the legacy alias. With a retriever attached,
# the agent reads Confluence through the RAG sources (synced from Confluence) instead of the live MCP
# tool, so either counts as reaching Confluence.
TOOL_ALIASES = {
    "search_confluence": ("confluence.page.search", "docs_rag_retriever_tool"),
    # The model chooses between searching and reading a page; either one reached live Confluence.
    "confluence.page.search": ("confluence.page.search", "confluence.page.read"),
}


def wanted_tools(expect_tool: str) -> tuple:
    """The UnifAI capability ids that satisfy a scenario's `expect_tool`."""
    return TOOL_ALIASES.get(expect_tool, (expect_tool,))


# Personas with a dedicated evaluation twin (WP-169): same groups, own ai-gateway token budget, so a campaign
# cannot exhaust the budget real demos and manual tests use. Scenarios keep the logical name (consultant-01);
# only the Keycloak sign-in uses the twin. The negative personas (no business role, no entitlement...) keep
# their own users. EVAL_PERSONAS=0 signs in as the logical persona (a cluster without the twins).
EVAL_TWINS = frozenset({"consultant-01", "sale-01", "adv-01", "finance-01", "board-01"})


def login_name(persona: str) -> str:
    """The Keycloak username a harness signs in with for the logical `persona`."""
    if persona in EVAL_TWINS and os.getenv("EVAL_PERSONAS", "1") != "0":
        return f"eval-{persona}"
    return persona


class UnifaiError(RuntimeError):
    pass


@dataclass
class UnifaiRun:
    session_id: str
    status: int
    reply: str = ""
    seconds: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


def routing_of(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The ai-gateway routing decision of the turn's last answer, or None.

    The LLM element asks the gateway why it answered (`/v1/routing-decisions/
    {request_id}`) and carries the JSON body on the assistant message as
    ``metadata.llm_response.routing`` (WP-148, chart `gatewayLLM.routingLookup`):
    ``{provider, model, kind, classification, fallback_used, fallback_from}``.
    None when the lookup is off or failed (it is best effort by design) or when
    the final answer merged several agents' results (no single routing).
    """
    candidates: List[Any] = list(reversed(state.get("messages") or []))
    candidates.insert(0, state.get("output"))
    for msg in candidates:
        if not isinstance(msg, dict) or msg.get("role", "assistant") != "assistant":
            continue
        routing = ((msg.get("metadata") or {}).get("llm_response") or {}).get("routing")
        if isinstance(routing, dict) and routing.get("provider"):
            return routing
    return None


def _reply_of(result: Dict[str, Any]) -> str:
    """The workflow's answer: `output` when set, else the last assistant message."""
    out = result.get("output")
    if isinstance(out, str) and out.strip():
        return out
    for msg in reversed(result.get("messages") or []):
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str) and msg["content"].strip():
            return msg["content"]
    return ""


class UnifaiTarget:
    def __init__(
        self,
        password: str,
        ui_url: Optional[str] = None,
        agent: str = "tekos",
        team_id: Optional[str] = None,
        team_name: Optional[str] = None,
    ) -> None:
        if not password:
            raise UnifaiError("DEMO_PERSONA_PASSWORD is required to sign in to UnifAI")
        self.ui_url = (ui_url or os.getenv("UNIFAI_URL", UNIFAI_URL)).rstrip("/")
        self.agent = agent
        self.team_id = team_id if team_id is not None else os.getenv("UNIFAI_TEAM_ID", "")
        self.team_name = team_name if team_name is not None else os.getenv("UNIFAI_TEAM_NAME", "")
        self._password = password
        self._clients: Dict[str, httpx.Client] = {}
        self._sessions: List[tuple] = []  # (persona, session_id), for cleanup

    # -- authentication -------------------------------------------------------

    def client(self, persona: str) -> httpx.Client:
        """A client whose cookie jar carries the persona's UnifAI session."""
        if persona in self._clients:
            return self._clients[persona]
        c = httpx.Client(follow_redirects=True, timeout=60, verify=VERIFY_TLS)
        state = base64.b64encode(json.dumps({"originalUrl": "/"}).encode()).decode()
        page = c.get(f"{self.ui_url}/api3/auth/login", params={"state": state})
        match = _LOGIN_FORM_RE.search(page.text)
        if not match:
            c.close()
            raise UnifaiError("UnifAI login did not reach Keycloak's kc-form-login")
        result = c.post(
            html.unescape(match.group(1)),
            data={"username": login_name(persona), "password": self._password, "credentialId": ""},
        )
        if "session" not in c.cookies or not str(result.url).startswith(self.ui_url):
            c.close()
            raise UnifaiError(f"UnifAI sign-in for {persona!r} failed (landed on {result.url})")
        self._clients[persona] = c
        if self.team_name and not self.team_id:
            # Resolved by the first persona that is a member; a non-member
            # (an entitlement check) leaves it unset, and the next member sets it.
            self.team_id = next((t["team_id"] for t in self.teams(persona) if t.get("name") == self.team_name), "")
        return c

    # -- team workspaces (identity service, /api3 on the UI route) ------------

    def teams(self, persona: str) -> List[Dict[str, Any]]:
        """The team workspaces `persona` belongs to (directly or through a group)."""
        resp = self.client(persona).get(f"{self.ui_url}/api3/teams/teams.list")
        resp.raise_for_status()
        return list(resp.json().get("teams") or [])

    def create_team(self, persona: str, name: str, groups: List[str]) -> Dict[str, Any]:
        """Create a team workspace owned by `persona` whose members are `groups`.

        Group ids are Keycloak group names (the identity service strips the
        leading `/` of full paths). Team names are unique: an existing name
        is a 400 from the identity service, raised here as UnifaiError.
        """
        resp = self.client(persona).post(
            f"{self.ui_url}/api3/teams/team.create",
            json={
                "name": name,
                "createdBy": persona,
                "members": [{"type": "group", "id": g, "display_name": g} for g in groups],
            },
        )
        if resp.status_code not in (200, 201):
            raise UnifaiError(f"team create {name!r} failed: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def anonymous_status(self, path: str) -> int:
        """HTTP status of an unauthenticated call (redirects not followed)."""
        with httpx.Client(follow_redirects=False, timeout=20, verify=VERIFY_TLS) as c:
            return c.get(f"{self.ui_url}{path}").status_code

    # -- workflows -----------------------------------------------------------

    def _team_params(self) -> Dict[str, str]:
        return {"teamId": self.team_id} if self.team_id else {}

    def _team_body(self) -> Dict[str, str]:
        return {"teamId": self.team_id} if self.team_id else {}

    def workflow_id(self, persona: str, name: Optional[str] = None) -> str:
        """Blueprint id of the workflow `name` (default: the agent's primary one)."""
        want = name or os.getenv("UNIFAI_WORKFLOW") or self.agent
        resp = self.client(persona).get(
            f"{self.ui_url}/api2/blueprints/available.blueprints.summary.get", params=self._team_params()
        )
        resp.raise_for_status()
        for item in resp.json():
            if item.get("name") == want:
                return item["blueprint_id"]
        raise UnifaiError(f"workflow {want!r} is not visible to {persona!r} in UnifAI")

    def visible_workflows(self, persona: str) -> List[str]:
        resp = self.client(persona).get(
            f"{self.ui_url}/api2/blueprints/available.blueprints.summary.get", params=self._team_params()
        )
        if resp.status_code == 403:  # TEAM_ACCESS_DENIED: not a member of the team workspace
            return []
        resp.raise_for_status()
        return sorted(i.get("name", "") for i in resp.json())

    # -- runs ----------------------------------------------------------------

    def create(self, persona: str, blueprint_id: str, tags: Optional[Dict[str, str]] = None) -> str:
        resp = self.client(persona).post(
            f"{self.ui_url}/api2/sessions/user.session.create",
            json={"blueprintId": blueprint_id, "metadata": {"tags": tags or {}}, **self._team_body()},
        )
        if resp.status_code != 200:
            raise UnifaiError(f"session create failed: {resp.status_code} {resp.text[:200]}")
        session_id = resp.json()
        self._sessions.append((persona, session_id))
        return session_id

    def run(
        self,
        persona: str,
        message: str,
        *,
        workflow: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
        timeout: float = 120,
    ) -> UnifaiRun:
        """One turn, consumed from the NDJSON stream (the path the UI uses).

        A non-streamed execute holds one HTTP request open for the whole run and
        was dropped by the UI proxy on long answers ("Server disconnected
        without sending a response", WP-154); the stream keeps the connection
        alive with heartbeats. Pass `session_id` to continue a conversation.
        """
        sid = session_id or self.create(persona, self.workflow_id(persona, workflow), tags)
        started = time.monotonic()
        last_state: Dict[str, Any] = {}
        tools: List[str] = []
        status = 200
        try:
            with self.client(persona).stream(
                "POST",
                f"{self.ui_url}/api2/sessions/user.session.execute",
                json={"sessionId": sid, "inputs": {"user_prompt": message}, "stream": True, **self._team_body()},
                timeout=timeout,
            ) as resp:
                status = resp.status_code
                if status != 200:
                    resp.read()
                    return UnifaiRun(sid, status, "", time.monotonic() - started, {"text": resp.text[:300]})
                for line in resp.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue
                    if chunk.get("type") == "tool_calling" and chunk.get("tool"):
                        tools.append(chunk["tool"])
                    state = chunk.get("state")
                    if chunk.get("type") == "complete" and isinstance(state, dict):
                        last_state = state
        except httpx.HTTPError as exc:
            return UnifaiRun(sid, 599, "", time.monotonic() - started, {"error": str(exc)})
        raw = dict(last_state)
        raw["tool_calls"] = tools
        raw["routing"] = routing_of(last_state)
        return UnifaiRun(sid, status, _reply_of(raw), time.monotonic() - started, raw)

    def stream(
        self,
        persona: str,
        message: str,
        *,
        workflow: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        timeout: float = 120,
    ) -> Iterator[Dict[str, Any]]:
        """NDJSON chunks of a streamed turn (heartbeats included)."""
        sid = self.create(persona, self.workflow_id(persona, workflow), tags)
        with self.client(persona).stream(
            "POST",
            f"{self.ui_url}/api2/sessions/user.session.execute",
            json={"sessionId": sid, "inputs": {"user_prompt": message}, "stream": True, **self._team_body()},
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                raise UnifaiError(f"stream failed: {resp.status_code}")
            for line in resp.iter_lines():
                if line.strip():
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue

    def collect(
        self,
        persona: str,
        message: str,
        *,
        workflow: Optional[str] = None,
        deadline_seconds: float = 150,
        stop_on: Optional[tuple] = None,
    ) -> Dict[str, Any]:
        """Drive one streamed turn under an OVERALL deadline and summarise it.

        The stream sends heartbeats, so a looping agent never trips the per-read
        timeout: the whole run is bounded here. Returns ``tools`` (tool names in
        order), ``reply`` (the final output), ``blob`` (str of every chunk),
        ``timed_out`` and ``stopped`` (a ``stop_on`` tool was seen).
        """
        deadline = time.monotonic() + deadline_seconds
        out: Dict[str, Any] = {"tools": [], "reply": "", "blob": "", "timed_out": False, "stopped": False}
        stream = self.stream(persona, message, workflow=workflow, timeout=deadline_seconds + 30)
        try:
            for chunk in stream:
                out["blob"] += str(chunk)
                if chunk.get("type") == "tool_calling" and chunk.get("tool"):
                    out["tools"].append(chunk["tool"])
                    if stop_on and chunk["tool"] in stop_on:
                        out["stopped"] = True
                        break
                state = chunk.get("state")
                if chunk.get("type") == "complete" and isinstance(state, dict):
                    out["reply"] = _reply_of(state) or out["reply"]
                if time.monotonic() > deadline:
                    out["timed_out"] = True
                    break
        finally:
            stream.close()
        return out

    def cleanup(self) -> tuple:
        """Delete every session this run created. Returns (deleted, failed)."""
        deleted = failed = 0
        for persona, sid in self._sessions:
            try:
                r = self.client(persona).delete(
                    f"{self.ui_url}/api2/sessions/session.delete", params={"sessionId": sid, **self._team_params()}
                )
                if r.status_code in (200, 204, 404):
                    deleted += 1
                else:
                    failed += 1
            except Exception:  # noqa: BLE001 - cleanup never fails a run
                failed += 1
        self._sessions.clear()
        return deleted, failed
