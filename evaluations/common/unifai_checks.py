"""Security-check building blocks for `security_checks.py --target unifai` (WP-155 wave 0).

Each factory returns a zero-argument check, parametrised by agent, so the five
agents that have security checks share one implementation instead of copies.
`CheckResult` is each agent's own dataclass (passed in): it must accept
`name, passed, detail` and `skipped`.

A check that cannot apply to UnifAI is replaced with `skip(...)`: it is
reported as skipped with its reason and excluded from the pass count, never
counted as a pass.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Sequence

import httpx


def skip(CheckResult: Any, name: str, why: str) -> Callable[[], Any]:
    def check() -> Any:
        return CheckResult(name, False, f"skipped: {why}", skipped=True)

    check.__name__ = name
    return check


def select(checks: Sequence[Callable], replacements: Dict[Callable, Callable], target: str) -> list:
    """The checks to run: the originals, or their UnifAI replacements under `--target unifai`."""
    if target != "unifai":
        return list(checks)
    return [replacements.get(c, c) for c in checks]


def _reaches(tools: Sequence[str], expect: Sequence[str]) -> bool:
    # A retriever-backed agent reads its sources through the RAG retriever instead of the live tool.
    return any(t in expect or "retriever" in t for t in tools)


def identity_forwarded(
    CheckResult: Any, unifai: Callable, persona: str, prompt: str, expect_tools: Sequence[str], timeout: float = 150
) -> Callable[[], Any]:
    """ADR-0032 on UnifAI: the signed-in person's own token must reach the tool gateway. The MCP
    gateway only serves a validated Keycloak JWT, so a tool call that returns a reply is direct
    evidence the token travelled UnifAI -> mcp-gateway."""
    name = "unifai_forwards_identity_to_the_gateways"

    def check() -> Any:
        run_ = unifai().collect(persona, prompt, deadline_seconds=timeout, stop_on=tuple(expect_tools))
        ok = _reaches(run_["tools"], expect_tools) and (bool(run_["reply"]) or run_["stopped"])
        return CheckResult(name, ok, f"tool_calls={run_['tools']} reply_len={len(run_['reply'])}")

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
