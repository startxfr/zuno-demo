"""Security-negative checks for the agent delegation chain (ADR-0401, ADR-0403, ADR-0406; WP-174).

Gateway-level checks: they call the MCP gateway the way UnifAI's A2A client will (the user's own
token plus `X-Zuno-Agent`/`X-Zuno-Task` naming the TARGET and `X-Zuno-Delegated-By`/
`X-Zuno-Delegation-Depth` naming the delegators), so they prove the platform's half of the contract
without needing the A2A server of WP-173. The behavioural half (a real delegation that runs, the
chain in the trace, an approval reaching the user) is WP-173/WP-174's live proof.

Same conventions as `unifai_checks.py`: each factory returns a zero-argument check, parametrised
by agent, and takes the caller's own `CheckResult`. A check that cannot apply is built with
`skip(...)` and is reported as skipped, never counted as a pass:

- the admitted release declares no such delegation target (nothing is enabled yet, which is the
  state on release v0.3.1);
- `delegation.allow_write` is true in the corp limits policy (writes are then governed by approval,
  ADR-0409, and the "no write tool" check would be wrong).
"""
from __future__ import annotations

import pathlib
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Union

import httpx
import yaml

from okf_release import agent_declaration, has_agent
from unifai_checks import skip

Headers = Callable[[str], Dict[str, str]]
Roots = Union[pathlib.Path, Sequence[pathlib.Path]]


def _roots(roots: Roots) -> List[pathlib.Path]:
    """Where agents/ and policies/ may be found: the repository or an extracted release, and the
    acceptance-gate Job, which mounts agent bundles under `/agents/<name>` and policies under
    `/gate/policies` (ansible/roles/agents/tasks/run_acceptance_gate.yml). Callers pass every layout
    that may apply; the first root holding the file wins."""
    return [roots] if isinstance(roots, pathlib.Path) else list(roots)


def chain_headers(*hops: str) -> Dict[str, str]:
    """The two delegation headers for delegators `agent:task`, outermost first."""
    return {"X-Zuno-Delegated-By": ",".join(hops), "X-Zuno-Delegation-Depth": str(len(hops))}


def _policy(roots: Roots, rel: str) -> dict:
    for root in _roots(roots):
        path = root / "policies" / rel
        if path.is_file():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def write_tools(roots: Roots) -> Set[str]:
    """Every name a write tool answers to: `access` is `read` or `write`, absent means write."""
    names: Set[str] = set()
    for entry in _policy(roots, "tools/tool-policy.yaml").get("tools") or []:
        if entry.get("access") != "read":
            names.update(n for n in (entry.get("tool"), entry.get("capability")) if n)
    return names


def allows_delegated_writes(roots: Roots) -> bool:
    """The corp flag; absent or unreadable means False, the gateway's own default."""
    return (_policy(roots, "limits/limits-policy.yaml").get("delegation") or {}).get("allow_write") is True


def declares_target(roots: Roots, delegator: str, target: str, target_task: str) -> bool:
    for root in _roots(roots):
        if not has_agent(root, delegator):
            continue
        try:
            targets = (agent_declaration(root, delegator).get("delegation") or {}).get("targets") or []
        except (OSError, ValueError):
            return False
        return any(t.get("agent") == target and t.get("task") == target_task for t in targets)
    return False


def _list(mcp_gateway_url: str, headers: Dict[str, str], timeout: float = 20) -> httpx.Response:
    return httpx.post(
        f"{mcp_gateway_url}/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=timeout,
    )


def _names(resp: httpx.Response) -> List[str]:
    return [t["name"] for t in (resp.json().get("result") or {}).get("tools") or []]


def _not_enabled(root: Roots, delegator: str, target: str, target_task: str) -> Optional[str]:
    if not declares_target(root, delegator, target, target_task):
        return f"the admitted release does not declare {delegator} -> {target}/{target_task} (delegation is not enabled)"
    return None


def delegation_surface(
    CheckResult: Any, *, root: Roots, mcp_gateway_url: str, auth_headers: Headers, persona: str,
    delegator: str, delegator_task: str, target: str, target_task: str,
) -> Callable[[], Any]:
    """ADR-0401/0403: a declared delegation, as an entitled user, reaches the target's surface; and
    ADR-0406: no write tool is on it while delegated writes are not allowed. The direct surface of the
    same agent task must list a write tool, so the absence cannot be a vacuous pass."""
    name = f"delegation_{delegator}_to_{target}_exposes_only_read_tools"
    why = _not_enabled(root, delegator, target, target_task)
    if why:
        return skip(CheckResult, name, why)
    if allows_delegated_writes(root):
        return skip(CheckResult, name, "delegation.allow_write is true: delegated writes are governed by approval (ADR-0409)")

    def check() -> Any:
        base = {**auth_headers(persona), "X-Zuno-Agent": target, "X-Zuno-Task": target_task,
                "X-Zuno-Data-Classification": "C3"}
        direct = _list(mcp_gateway_url, base)
        chained = _list(mcp_gateway_url, {**base, **chain_headers(f"{delegator}:{delegator_task}")})
        if direct.status_code != 200 or chained.status_code != 200:
            return CheckResult(name, False, f"direct={direct.status_code} delegated={chained.status_code}")
        writes, direct_names, chained_names = write_tools(root), set(_names(direct)), set(_names(chained))
        leaked = sorted(chained_names & writes)
        ok = bool(chained_names) and not leaked and bool(direct_names & writes) and chained_names <= direct_names
        return CheckResult(
            name, ok,
            f"delegated={sorted(chained_names)} direct_write_tools={sorted(direct_names & writes)} "
            f"write_tools_on_the_delegated_surface={leaked}",
        )

    check.__name__ = name
    return check


def delegation_refused(
    CheckResult: Any, *, name: str, root: Roots, mcp_gateway_url: str, auth_headers: Headers,
    persona: str, agent: str, task: str, hops: List[str], malformed: Optional[Dict[str, str]] = None,
    requires: Optional[tuple] = None,
) -> Callable[[], Any]:
    """The gateway must answer 403 to this chain. `hops` are the delegators (outermost first);
    `malformed` replaces the headers with exactly these values. `requires=(delegator, target, task)`
    skips the check unless the release declares that delegation (so a refusal is never confused with
    "nothing is enabled")."""
    if requires:
        why = _not_enabled(root, *requires)
        if why:
            return skip(CheckResult, name, why)

    def check() -> Any:
        headers = {**auth_headers(persona), "X-Zuno-Agent": agent, "X-Zuno-Task": task,
                   "X-Zuno-Data-Classification": "C3", **(malformed if malformed is not None else chain_headers(*hops))}
        resp = _list(mcp_gateway_url, headers)
        detail = ""
        try:
            detail = str(resp.json().get("detail", ""))[:160]
        except ValueError:
            pass
        return CheckResult(name, resp.status_code == 403, f"status={resp.status_code} {detail}".strip())

    check.__name__ = name
    return check


def tekos_to_arkos_checks(
    CheckResult: Any, *, root: Roots, mcp_gateway_url: str, auth_headers: Headers,
    allowed_persona: str = "eval-consultant-01", unentitled_persona: str = "tekos-entitlement-only-user-01",
) -> List[Callable[[], Any]]:
    """The WP-174 gateway scenarios for the first declared delegation, Tekos to Arkos."""
    D, DT = "tekos", "answer-technical-question"
    T, TT = "arkos", "draft-architecture-testimonial"
    common = dict(root=root, mcp_gateway_url=mcp_gateway_url, auth_headers=auth_headers)
    need = (D, T, TT)
    return [
        delegation_surface(CheckResult, persona=allowed_persona, delegator=D, delegator_task=DT, target=T,
                           target_task=TT, **common),
        delegation_refused(CheckResult, name="delegation_refused_when_the_user_lacks_the_target_entitlement",
                           persona=unentitled_persona, agent=T, task=TT, hops=[f"{D}:{DT}"], requires=need, **common),
        delegation_refused(CheckResult, name="delegation_refused_for_a_target_the_delegator_does_not_declare",
                           persona=allowed_persona, agent=D, task=DT, hops=[f"{T}:{TT}"], requires=need, **common),
        delegation_refused(CheckResult, name="delegation_refused_beyond_the_depth_limit",
                           persona=allowed_persona, agent=T, task=TT, hops=["comage:check-deal-status", f"{D}:{DT}"],
                           requires=need, **common),
        delegation_refused(CheckResult, name="delegation_refused_on_a_cycle",
                           persona=allowed_persona, agent=T, task=TT, hops=[f"{T}:{TT}", f"{D}:{DT}"],
                           requires=need, **common),
        delegation_refused(CheckResult, name="delegation_refused_when_the_depth_header_disagrees",
                           persona=allowed_persona, agent=T, task=TT, hops=[], requires=need,
                           malformed={"X-Zuno-Delegated-By": f"{D}:{DT}", "X-Zuno-Delegation-Depth": "2"}, **common),
        delegation_refused(CheckResult, name="delegation_refused_with_half_a_chain",
                           persona=allowed_persona, agent=T, task=TT, hops=[], requires=need,
                           malformed={"X-Zuno-Delegated-By": f"{D}:{DT}"}, **common),
    ]
