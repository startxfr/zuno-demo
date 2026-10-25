"""Security-check building blocks for the agents' `security_checks.py` (WP-155 wave 0; UnifAI
is the only evaluation target since WP-156).

Each factory returns a zero-argument check, parametrised by agent, so the five
agents that have security checks share one implementation instead of copies.
`CheckResult` is each agent's own dataclass (passed in): it must accept
`name, passed, detail` and `skipped`.

A check that cannot apply to UnifAI (e.g. a placeholder agent's chat turn)
is declared with `skip(...)`: it is
reported as skipped with its reason and excluded from the pass count, never
counted as a pass.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, Optional, Sequence

import httpx


def skip(CheckResult: Any, name: str, why: str) -> Callable[[], Any]:
    def check() -> Any:
        return CheckResult(name, False, f"skipped: {why}", skipped=True)

    check.__name__ = name
    return check


def _reaches(tools: Sequence[str], expect: Sequence[str]) -> bool:
    # A retriever-backed agent reads its sources through the RAG retriever instead of the live tool.
    return any(t in expect or "retriever" in t for t in tools)


def identity_forwarded(
    CheckResult: Any,
    unifai: Callable,
    persona: str,
    prompt: str,
    expect_tools: Sequence[str],
    timeout: float = 150,
    attempts: int = 1,
) -> Callable[[], Any]:
    """ADR-0032 on UnifAI: the signed-in person's own token must reach the tool gateway. The MCP
    gateway only serves a validated Keycloak JWT, so a tool call that returns a reply is direct
    evidence the token travelled UnifAI -> mcp-gateway.

    The agent decides whether to call a tool, so a model that answers from its own knowledge
    proves nothing either way. `attempts` (default 1) allows that many turns; the check passes on
    the first turn that reaches an expected tool and FAILS when none does, and the detail line
    names every turn so a pass on a later attempt is never hidden."""
    name = "unifai_forwards_identity_to_the_gateways"

    def check() -> Any:
        seen = []
        for attempt in range(1, max(1, attempts) + 1):
            run_ = unifai().collect(persona, prompt, deadline_seconds=timeout, stop_on=tuple(expect_tools))
            ok = _reaches(run_["tools"], expect_tools) and (bool(run_["reply"]) or run_["stopped"])
            seen.append(f"tool_calls={run_['tools']} reply_len={len(run_['reply'])}")
            if ok:
                break
        if attempts <= 1:
            return CheckResult(name, ok, seen[0])
        return CheckResult(name, ok, f"attempt={len(seen)}/{attempts}: " + " | ".join(seen))

    check.__name__ = name
    return check


def client_identity_header_refused(CheckResult: Any, unifai: Callable) -> Callable[[], Any]:
    """ADR-0033 on UnifAI: there is no body field to forge, but UnifAI trusts an internal
    `X-Authenticated-User` header from inside the cluster. From outside, a caller without a
    session who sends it must still be refused (the UI route deletes it)."""
    name = "unifai_ignores_a_client_supplied_identity_header"

    def check() -> Any:
        with httpx.Client(follow_redirects=False, timeout=20, verify=False) as c:
            resp = c.post(
                f"{unifai().ui_url}/api2/sessions/user.session.create",
                headers={"X-Authenticated-User": "admin"},
                json={"blueprintId": "x"},
            )
        return CheckResult(name, resp.status_code == 401, f"status={resp.status_code}")

    check.__name__ = name
    return check


def entitlement_denied(
    CheckResult: Any,
    unifai: Callable,
    *,
    agent: str,
    task: str,
    persona: str,
    mcp_gateway_url: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> Callable[[], Any]:
    """ADR-0040 converse case on UnifAI: `persona` has the business role but not `agent_<agent>`.
    The agent must not appear for it AND the MCP gateway must refuse the agent declaration."""
    name = "business_role_without_entitlement_denied_by_unifai"

    def check() -> Any:
        visible = agent in unifai().visible_workflows(persona)
        resp = httpx.post(
            f"{mcp_gateway_url}/mcp",
            headers={**auth_headers(persona), "X-Zuno-Agent": agent, "X-Zuno-Task": task},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            timeout=20,
        )
        return CheckResult(
            name, (not visible) and resp.status_code == 403, f"workflow_visible={visible} mcp_status={resp.status_code}"
        )

    check.__name__ = name
    return check


def image_tool_boundary(
    CheckResult: Any,
    unifai: Callable,
    *,
    name: str,
    persona: str,
    prompt: str,
    timeout: float = 150,
) -> Callable[[], Any]:
    """ADR-0415/ADR-0516 on UnifAI: an agent whose task never declares `image.generation.create`
    may call the diagram tool but must never reach the SDXL tool nor return a PNG. The run is
    bounded by an overall deadline (heartbeats defeat the per-read timeout); not seeing the
    image tool before the deadline is still a pass."""

    def check() -> Any:
        run_ = unifai().collect(persona, prompt, deadline_seconds=timeout)
        ok = "image.generation.create" not in run_["tools"] and "image/png" not in run_["blob"]
        return CheckResult(name, ok, f"tool_calls={run_['tools']}")

    check.__name__ = name
    return check


def marketing_image_boundary(
    CheckResult: Any, unifai: Callable, *, name: str, persona: str, chart_prompt: str, marketing_prompt: str,
    timeout: float = 150,
) -> Callable[[], Any]:
    """Comage on UnifAI: a plain chart ask never produces a photorealistic image, an explicit
    marketing-visual ask does (the image tool is called or a PNG comes back)."""

    def check() -> Any:
        chart = unifai().collect(persona, chart_prompt, deadline_seconds=timeout)
        chart_ok = "image.generation.create" not in chart["tools"] and "image/png" not in chart["blob"]
        mkt = unifai().collect(persona, marketing_prompt, deadline_seconds=timeout, stop_on=("image.generation.create",))
        mkt_ok = mkt["stopped"] or "image/png" in mkt["blob"] or "image.generation.create" in mkt["tools"]
        return CheckResult(name, chart_ok and mkt_ok, f"chart_tools={chart['tools']} marketing_tools={mkt['tools']}")

    check.__name__ = name
    return check


def cross_user_isolation(CheckResult: Any, unifai: Callable, *, owner: str, other: str) -> Callable[[], Any]:
    """ADR-0583 on UnifAI: object-level authorisation, proven with two real people. `other` (not
    a member of `owner`'s team workspace, no share) must get the same answer for `owner`'s
    session, team and blueprint as for an identifier that does not exist, and must not see a
    team workspace's blueprints through it. A denial that differs from "missing" tells `other`
    the object exists."""
    name = "unifai_denies_another_users_objects_like_missing_ones"

    def check() -> Any:
        u = unifai()
        ui = u.ui_url
        co, cx = u.client(owner), u.client(other)
        problems = []
        teams = [t for t in u.teams(owner) if t.get("team_id") not in {x.get("team_id") for x in u.teams(other)}]
        if not teams:
            return CheckResult(name, False, f"skipped: {owner} has no team workspace {other} is outside of", skipped=True)
        team_id = teams[0]["team_id"]
        missing = str(uuid.uuid4())

        def same(label: str, call: Callable[[str], Any]) -> None:
            denied, absent = call(team_id), call(missing)
            if denied.status_code != absent.status_code or denied.text != absent.text:
                problems.append(f"{label}: {denied.status_code} vs {absent.status_code}")

        same("team.get", lambda t: cx.get(f"{ui}/api3/teams/team.get", params={"teamId": t}))
        same("team.delete", lambda t: cx.delete(f"{ui}/api3/teams/team.delete", params={"teamId": t}))
        blueprints = co.get(f"{ui}/api2/blueprints/available.blueprints.summary.get", params={"teamId": team_id})
        first = (blueprints.json() or [{}])[0].get("blueprint_id") if blueprints.status_code == 200 else None
        if first:
            r = cx.get(f"{ui}/api2/blueprints/blueprint.info.get", params={"blueprintId": first, "teamId": team_id})
            if r.status_code not in (403, 404):
                problems.append(f"blueprint.info.get through the team: {r.status_code}")
            sid = u.create(owner, first)
            for ep in ("session.meta", "session.chat.get", "session.state.get"):
                same(ep, lambda t, ep=ep: cx.get(f"{ui}/api2/sessions/{ep}", params={"sessionId": sid if t == team_id else t}))
            u.cleanup()
        return CheckResult(name, not problems, "; ".join(problems) or f"checked as {other} against {owner}")

    check.__name__ = name
    return check


def a2a_gateway_denies_unentitled(
    CheckResult: Any,
    *,
    agent: str,
    persona: str,
    a2a_gateway_url: str,
    auth_headers: Callable[[str], Dict[str, str]],
) -> Callable[[], Any]:
    """ADR-0585: the A2A gateway answers with the caller's identity. Anonymous is refused (401) and
    a persona without the agent's group gets exactly the answer for an agent that does not exist
    (no tell that the agent is served), and no model call is made for it."""
    name = "a2a_gateway_denies_unentitled_callers_like_unknown_agents"

    def check() -> Any:
        body = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}}
        base = a2a_gateway_url.rstrip("/")
        anon = httpx.post(f"{base}/agents/{agent}/", json=body, timeout=20)
        denied = httpx.post(f"{base}/agents/{agent}/", json=body, headers=auth_headers(persona), timeout=20)
        unknown = httpx.post(f"{base}/agents/{uuid.uuid4().hex}/", json=body, headers=auth_headers(persona), timeout=20)
        ok = anon.status_code == 401 and denied.status_code == unknown.status_code == 404 and denied.json() == unknown.json()
        return CheckResult(name, ok, f"anonymous={anon.status_code} denied={denied.status_code} unknown={unknown.status_code}")

    check.__name__ = name
    return check
