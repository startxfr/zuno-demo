"""UnifAI target for the agent evaluations (WP-154, ADR-0573).

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


class UnifaiError(RuntimeError):
    pass


@dataclass
class UnifaiRun:
    session_id: str
    status: int
    reply: str = ""
    seconds: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


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
        self, password: str, ui_url: str = UNIFAI_URL, agent: str = "tekos", team_id: Optional[str] = None
    ) -> None:
        if not password:
            raise UnifaiError("DEMO_PERSONA_PASSWORD is required to sign in to UnifAI")
        self.ui_url = ui_url.rstrip("/")
        self.agent = agent
        self.team_id = team_id if team_id is not None else os.getenv("UNIFAI_TEAM_ID", "")
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
            data={"username": persona, "password": self._password, "credentialId": ""},
        )
        if "session" not in c.cookies or not str(result.url).startswith(self.ui_url):
            c.close()
            raise UnifaiError(f"UnifAI sign-in for {persona!r} failed (landed on {result.url})")
        self._clients[persona] = c
        return c

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
