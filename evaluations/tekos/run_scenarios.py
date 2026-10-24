#!/usr/bin/env python3
"""Runs an agent's 20 acceptance scenarios (scenarios.yaml, in this same
directory by default) against a live deployment and reports the pass rate
against the 75% threshold (ADR-0027, ADR-0028). See README.md for required
environment variables.

ADR-0342/WP-31: genuinely shared across every agent, not copied per agent -
parameterized by the AGENT env var (default "tekos", preserving this
module's original behavior unchanged when unset). evaluations/arkos/ (and
every later agent slice) reuses this exact file via a thin wrapper that
sets AGENT before delegating to main() - see that directory's own
run_scenarios.py for the two-line pattern.

WP-156: the agents are served by UnifAI (ADR-0561), the only evaluation
target. Chat-shaped scenarios run through UnifAI's own session API
(evaluations/common/unifai_target.py); scenarios about shared platform
services (Keycloak, MCP gateway, model routing, namespace isolation) call
those services directly.

This cannot be executed in the sandbox this repo was built in (no live
cluster) - it is written to be genuinely runnable once one exists, not a
mock. Each `type` in scenarios.yaml maps to exactly one handler function
below; add a new scenario by adding a YAML entry plus (if it's a new type)
a handler.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx
import yaml

try:
    # Present alongside this file once mounted into the stresstest Job pod
    # (ansible/roles/day3/kustomize/stresstest-scripts/kustomization.yaml
    # projects platform/testing/day2_report.py unprefixed into the same
    # flat directory) - absent for a standalone `cd evaluations/tekos &&
    # python3 run_scenarios.py` dev run outside that pod, which is fine:
    # verbose per-scenario logging is a pod-log convenience, not required
    # for this file's own pass/fail correctness.
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass


# ADR-0342/WP-31: which agent this run evaluates - drives the UnifAI
# workflow/team names and (via TASK_NAME below) which OKF task name is
# declared to the MCP Gateway. Defaults to "tekos" so every existing direct
# invocation of this file (`cd evaluations/tekos && python3 run_scenarios.py`,
# with no AGENT set) behaves exactly as before this parameterization.
AGENT = os.getenv("AGENT", "tekos")
# The OKF task this agent's evaluation exercises (app/registry.py's
# TaskDefinition.name) - required by _invoke_tool's X-Zuno-Task header
# (ADR-0036). Each agent's own README documents its value; defaulting to
# Tekos's real task name keeps the unparameterized case unchanged.
TASK_NAME = os.getenv("TASK_NAME", "answer-technical-question")

# WP-154 (ADR-0573) introduced a `--target`/EVAL_TARGET switch between UnifAI
# and the legacy agent stack; WP-156 retired the latter, so "unifai" is the
# only value left. The switch is still accepted (the acceptance-gate and
# stresstest Jobs set EVAL_TARGET=unifai) so an explicit request for anything
# else fails loudly instead of silently evaluating UnifAI.
TARGET = "unifai"
_requested_target = os.getenv("EVAL_TARGET") or TARGET
if "--target" in sys.argv:
    _i = sys.argv.index("--target")
    if _i + 1 < len(sys.argv):
        _requested_target = sys.argv[_i + 1]
if _requested_target != TARGET:
    raise SystemExit(
        f"run_scenarios.py: unsupported evaluation target {_requested_target!r} - "
        f"{TARGET!r} is the only target since WP-156 retired the legacy agent stack"
    )

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://keycloak.apps.mycluster.example.com")
# No scenario calls it any more: kept only as the base-domain hint
# platform/testing/quota_429.py derives the quota-demo route from
# (https://<agent>.apps.<base-domain>) when neither QUOTA_DEMO_URL nor
# CLUSTER_BASE_DOMAIN is set.
FRONTEND_URL = os.getenv("FRONTEND_URL", f"https://{AGENT}.apps.mycluster.example.com")
# Shared across every agent (ADR-0342's generic dispatch) - never
# agent-specific.
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc.cluster.local:8080")
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")


REALM = "zuno"
# Shared demo-persona password (ADR-0041) - never hardcoded; read from the
# same place `make configure keycloak` puts it (an operator running this
# script fetches it once, e.g.
# `vault kv get -field=password secret/zuno/keycloak/demo-personas`).
# ansible/roles/keycloak/README.md's "Two integration fixes" note explains
# why every fixture user's credential is non-temporary.
DEMO_PASSWORD = os.getenv("DEMO_PERSONA_PASSWORD")
# Persona tokens come from the dedicated zuno-evaluations client (WP-156); its secret is never hardcoded:
# `oc -n zuno-auth get secret zuno-evaluations-client-secret -o jsonpath='{.data.client_secret}'`.
TOKEN_CLIENT_ID = os.getenv("EVAL_CLIENT_ID", "zuno-evaluations")
TOKEN_CLIENT_SECRET = os.getenv("EVAL_CLIENT_SECRET")


@dataclass
class ScenarioResult:
    id: int
    title: str
    passed: bool
    detail: str = ""
    # WP-154: a scenario that cannot apply to UnifAI (e.g. a placeholder
    # agent's chat turn) is reported and excluded from the pass rate, never
    # counted as a pass.
    skipped: bool = False


_token_cache: Dict[str, str] = {}


def _login_name(persona: str) -> str:
    from unifai_target import login_name  # shared transport (evaluations/common)

    return login_name(persona)


def get_token(persona: str) -> str:
    """Resource Owner Password Credentials grant against the evaluation
    client - appropriate for an automated evaluation harness acting on
    behalf of fixture personas, not for real user login (which goes through
    the UnifAI UI's own browser OIDC flow, see unifai_target.py). The token
    is for the platform services called directly below (MCP gateway,
    ai-gateway); UnifAI itself is driven through a session cookie.
    """
    if persona in _token_cache:
        return _token_cache[persona]
    if not TOKEN_CLIENT_SECRET:
        raise RuntimeError("EVAL_CLIENT_SECRET (zuno-evaluations) is required to obtain persona tokens")
    if not DEMO_PASSWORD:
        raise RuntimeError("DEMO_PERSONA_PASSWORD is required to obtain persona tokens")

    resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": TOKEN_CLIENT_ID,
            "client_secret": TOKEN_CLIENT_SECRET,
            "username": _login_name(persona),
            "password": DEMO_PASSWORD,
            "scope": "openid",
        },
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    _token_cache[persona] = token
    return token


def auth_headers(persona: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {get_token(persona)}"}


# --------------------------------------------------------------------------
# Shared platform-service handlers: these scenarios exercise Keycloak, the
# MCP gateway and the model-routing config directly, whatever serves the
# agents.
# --------------------------------------------------------------------------


def _decode_claims_without_verifying(token: str) -> Dict[str, Any]:
    """Decodes a JWT's payload segment for claim inspection only - no
    signature verification. Safe here specifically because the token was
    just obtained directly from Keycloak over TLS in get_token() above; this
    never validates an externally-supplied token (that's auth.py's job in
    every service, exercised by test_auth.py instead).
    """
    import base64

    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def keycloak_login(s: Dict[str, Any]) -> ScenarioResult:
    """ADR-0053 "Keycloak login/claims": proves both that the persona can
    authenticate at all, and that the resulting token actually carries the
    group claims (ADR-0040's business-role/agent-entitlement groups) every
    downstream authorization decision (MCP and AI gateways) depends on -
    login succeeding with an empty/wrong claim set would pass a
    "login"-only check while still breaking every scenario after it.
    """
    try:
        token = get_token(s["persona"])
        claims = _decode_claims_without_verifying(token)
        groups = [g.lstrip("/") for g in claims.get("groups", [])]
        expected = s.get("expect_groups", [])
        missing = [g for g in expected if g not in groups]
        ok = bool(token) and not missing
        return ScenarioResult(s["id"], s["title"], ok, f"groups={groups} missing={missing}")
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))


def _invoke_tool(persona: str, tool: str, arguments: Dict[str, Any], classification: str = "C1") -> httpx.Response:
    # ADR-0036: X-Zuno-Agent/X-Zuno-Task are required - every scenario here
    # calls the gateway as if it were Tekos's one real task, since this
    # harness is evaluations/tekos/. A tool this task doesn't declare (e.g.
    # scenario 12's salesforce.opportunity.read, scenario 18's
    # git.repository.delete) is still correctly denied by the gateway's
    # agent_declaration factor - no per-scenario override needed.
    return httpx.post(
        f"{MCP_GATEWAY_URL}/v1/tools/{tool}/invoke",
        headers={
            **auth_headers(persona),
            "X-Zuno-Data-Classification": classification,
            "X-Zuno-Agent": AGENT,
            "X-Zuno-Task": TASK_NAME,
        },
        json=arguments,
        timeout=15,
    )


def mcp_gateway_denied(s: Dict[str, Any]) -> ScenarioResult:
    resp = _invoke_tool(s["persona"], s["tool"], s["arguments"], classification="C2")
    ok = resp.status_code == s["expect_status"]
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code} expected={s['expect_status']}")


def mcp_gateway_unknown_tool(s: Dict[str, Any]) -> ScenarioResult:
    resp = _invoke_tool(s["persona"], s["tool"], {})
    ok = resp.status_code == s["expect_status"]
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code} expected={s['expect_status']}")


def model_router_fails_closed(s: Dict[str, Any]) -> ScenarioResult:
    # No HTTP surface exposes ModelRouter directly; verified against
    # policies/data-classification/classification.yaml + provider-routing.yaml
    # (every C3 domain must map to a provider list where only "local" is
    # eligible). This is a config-consistency check, runnable without a
    # live cluster, hence its inclusion despite the other handlers needing one.
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    routing = yaml.safe_load((repo_root / "platform/ai-gateway/provider-routing.yaml").read_text())
    # ADR-0412: two local providers exist (qwen + gpt-oss), so the invariant
    # is kind-based - every C3-eligible provider must be kind "local", and
    # at least one must exist - rather than a hardcoded ["local"] name list.
    c3_providers = [p for p in routing.get("providers", []) if "C3" in p.get("eligible_for", [])]
    c3_names = [p["name"] for p in c3_providers]
    ok = bool(c3_providers) and all(p.get("kind") == "local" for p in c3_providers)
    return ScenarioResult(s["id"], s["title"], ok, f"C3-eligible providers={c3_names}")


def model_router_prefers_local(s: Dict[str, Any]) -> ScenarioResult:
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    routing = yaml.safe_load((repo_root / "platform/ai-gateway/provider-routing.yaml").read_text())
    providers = routing.get("providers", [])
    # kind-based, not name-based - same reasoning as c3_requests_fail_closed
    # above. What this scenario guarantees is that a C1 call reaches a LOCAL
    # provider first; which local one is a transport detail that moves with
    # routing decisions. This asserted providers[0]["name"] == "local" and
    # broke when WP-076/ADR-0521 put `local-maas` first (MaaS became the
    # preferred local transport) - a false failure, since the head of the
    # list was still local. Do not re-hardcode a name here.
    first = providers[0] if providers else {}
    ok = bool(providers) and first.get("kind") == "local" and "C1" in first.get("eligible_for", [])
    return ScenarioResult(
        s["id"],
        s["title"],
        ok,
        f"first_provider={first.get('name')} kind={first.get('kind')} eligible_for={first.get('eligible_for')}",
    )


def agent_isolation_placeholder_empty(s: Dict[str, Any]) -> ScenarioResult:
    # Requires the Kubernetes Python client and in-cluster config (the gate
    # Job's own ServiceAccount token) - the one scenario that inspects
    # cluster state directly rather than an HTTP API. Uses the `kubernetes`
    # package rather than shelling out to `oc`/`kubectl`: the gate Job's
    # image (python:3.12-slim) does not ship either binary, which made this
    # scenario fail with a spurious "No such file or directory" on every
    # run regardless of actual cluster state. ADR-0329 (supersedes
    # ADR-0023): placeholder agents no longer get their own namespace, so
    # this checks for zero pods carrying
    # each placeholder agent's zuno.io/agent label inside the single shared
    # namespace instead of per-agent namespace emptiness.
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config

    try:
        k8s_config.load_incluster_config()
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, f"cannot load in-cluster kube config: {exc}")

    v1 = k8s_client.CoreV1Api()
    ns = s["namespace"]
    all_empty = True
    details = []
    for agent in s["agents"]:
        try:
            pods = v1.list_namespaced_pod(ns, label_selector=f"zuno.io/agent={agent}")
            pod_count = len(pods.items)
        except Exception as exc:
            details.append(f"{agent}: error ({exc})")
            all_empty = False
            continue
        details.append(f"{agent}: {pod_count} pods")
        if pod_count > 0:
            all_empty = False
    return ScenarioResult(s["id"], s["title"], all_empty, "; ".join(details))


# --------------------------------------------------------------------------
# UnifAI handlers (WP-154, the only target since WP-156): the scenarios about
# the agents themselves, served by UnifAI's own session API
# (evaluations/common/unifai_target.py). The `u_` prefix marks them. A
# scenario type kept from the legacy stack (portal tiles, BFF JWT checks)
# gets its UnifAI equivalent, or is reported as skipped with its reason when
# none exists.
# --------------------------------------------------------------------------

_unifai_target = None

# Tool-name aliases (capability ids, retriever fallback) live in the shared transport module.


def _unifai_tempo_rag_searches(run_id: str, tempo_url: str):
    from unifai_target import tempo_rag_searches  # lazy, same reason as _unifai()

    return tempo_rag_searches(run_id, tempo_url)


def _unifai():
    global _unifai_target
    if _unifai_target is None:
        from unifai_target import UnifaiTarget  # lazy: only the unifai target ships this file

        _unifai_target = UnifaiTarget(DEMO_PASSWORD, agent=AGENT)
    return _unifai_target


def _skip(s: Dict[str, Any], why: str) -> ScenarioResult:
    return ScenarioResult(s["id"], s["title"], False, f"skipped: {why}", skipped=True)


_PLACEHOLDER_WHY = "placeholder agent (ADR-0007): it has no UnifAI workflow to chat with"


def _unifai_wanted_tools(expect_tool: str) -> tuple:
    from unifai_target import wanted_tools  # shared transport (evaluations/common)

    return wanted_tools(expect_tool)


def _unifai_placeholder_skip(s: Dict[str, Any]) -> bool:
    """True when this agent is a `status: placeholder` OKF bundle: no UnifAI workflow exists for
    it, so a scenario that needs a live chat turn cannot run (the blocked-chat scenarios prove
    the boundary instead)."""
    return _agent_status() == "placeholder"


def _agent_status() -> str:
    # WP-165: the bundle comes from the admitted agents release in a checkout
    # (evaluations/common/okf_release.py), from the Job's mounts otherwise.
    # Flattened into /gate in the Jobs, so both locations are searched.
    _here = pathlib.Path(__file__).resolve().parent
    for candidate in (_here, _here.parent / "common"):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    from okf_release import agent_declaration, okf_root

    try:
        zuno = agent_declaration(okf_root(pathlib.Path(__file__).resolve().parents[2]), AGENT)
        return str(zuno.get("status", "")).strip()
    except Exception:  # noqa: BLE001 - unknown status means "assume active"
        return ""


def u_portal_lists_all_agents(s: Dict[str, Any]) -> ScenarioResult:
    if _unifai_placeholder_skip(s):
        return _skip(s, _PLACEHOLDER_WHY)
    names = _unifai().visible_workflows(s["persona"])
    ok = AGENT in names
    return ScenarioResult(s["id"], s["title"], ok, f"visible workflows={names}")


def u_portal_requires_login(s: Dict[str, Any]) -> ScenarioResult:
    status = _unifai().anonymous_status("/api2/blueprints/available.blueprints.summary.get")
    return ScenarioResult(s["id"], s["title"], status == 401, f"anonymous status={status}")


def u_portal_tile_state(s: Dict[str, Any]) -> ScenarioResult:
    # A "tile" is a workflow visible to the persona. UnifAI scopes visibility
    # by owner/team, not by Keycloak group (the entitlement by group is enforced
    # at the gateways, ADR-0562), so a disabled tile is proven twice: no
    # workflow listed AND the MCP gateway refusing the agent for that persona.
    if s.get("expect_placeholder"):
        return _skip(s, "UnifAI has no placeholder agent tiles")
    names = _unifai().visible_workflows(s["persona"])
    visible = s["agent"] in names
    if s["expect_enabled"]:
        return ScenarioResult(s["id"], s["title"], visible, f"visible workflows={names}")
    resp = httpx.post(
        f"{MCP_GATEWAY_URL}/mcp",
        headers={**auth_headers(s["persona"]), "X-Zuno-Agent": s["agent"], "X-Zuno-Task": TASK_NAME},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=15,
    )
    refused = resp.status_code == 403
    return ScenarioResult(
        s["id"], s["title"], (not visible) and refused, f"visible={visible} mcp_status={resp.status_code}"
    )


def u_chat_basic_qa(s: Dict[str, Any]) -> ScenarioResult:
    if _unifai_placeholder_skip(s):
        return _skip(s, _PLACEHOLDER_WHY)
    t = _unifai()
    timeout = s.get("timeout_seconds", 120)
    first = t.run(s["persona"], s["message"], timeout=timeout)
    if first.status != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={first.status}")
    ok = bool(first.reply)
    detail = f"reply_len={len(first.reply)} seconds={first.seconds:.1f} (citations: RAG source not deployed yet)"
    follow_up = s.get("follow_up")
    if ok and follow_up:
        second = t.run(s["persona"], follow_up, session_id=first.session_id, timeout=timeout)
        follow_ok = second.status == 200 and bool(second.reply)
        ok = ok and follow_ok
        detail += f" follow_up_status={second.status} follow_up_ok={follow_ok}"
    return ScenarioResult(s["id"], s["title"], ok, detail)


def u_chat_first_token_latency(s: Dict[str, Any]) -> ScenarioResult:
    if _unifai_placeholder_skip(s):
        return _skip(s, _PLACEHOLDER_WHY)
    start = time.monotonic()
    first_token_at: Optional[float] = None
    try:
        for chunk in _unifai().stream(s["persona"], s["message"], timeout=60):
            if chunk.get("type") == "llm_token":
                first_token_at = time.monotonic()
                break
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    if first_token_at is None:
        return ScenarioResult(s["id"], s["title"], False, "no token received")
    elapsed = first_token_at - start
    return ScenarioResult(
        s["id"], s["title"], elapsed <= s["max_seconds"], f"first_token_seconds={elapsed:.2f} max={s['max_seconds']}"
    )


def u_chat_streaming(s: Dict[str, Any]) -> ScenarioResult:
    if _unifai_placeholder_skip(s):
        return _skip(s, _PLACEHOLDER_WHY)
    kinds: Dict[str, int] = {}
    try:
        for chunk in _unifai().stream(s["persona"], s["message"], timeout=s.get("timeout_seconds", 120)):
            kinds[chunk.get("type", "?")] = kinds.get(chunk.get("type", "?"), 0) + 1
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    ok = kinds.get("llm_token", 0) > 0 and kinds.get("complete", 0) > 0
    return ScenarioResult(s["id"], s["title"], ok, f"events={kinds}")


_UNIFAI_LIVE_READ_TOOLS = {"comage": "salesforce.opportunity.read"}


def u_chat_triggers_tool(s: Dict[str, Any]) -> ScenarioResult:
    if _unifai_placeholder_skip(s):
        return _skip(s, _PLACEHOLDER_WHY)
    # comage's scenario 10 has no `expect_tool` (it predates UnifAI, which proves the live
    # read by the tool call itself).
    want = _unifai_wanted_tools(s.get("expect_tool") or _UNIFAI_LIVE_READ_TOOLS.get(AGENT, ""))
    try:
        # Overall deadline: heartbeats keep a looping agent from tripping the per-read timeout.
        run_ = _unifai().collect(
            s["persona"], s["message"], deadline_seconds=s.get("timeout_seconds", 180), stop_on=want
        )
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    tools = run_["tools"]
    return ScenarioResult(
        s["id"], s["title"], any(t in want for t in tools), f"expected one of {list(want)} tool_calls={tools}"
    )


# A page of the tekos RAG sources (space SXSI, tree "Technologie : Satellite"), and what it
# is called; the answer must name it. Override for another corpus. Other agents ask their own
# scenario's `query` and only require that the retriever was used, unless UNIFAI_RAG_EXPECT is set.
_TEKOS_RAG_QUESTION = (
    "What does the internal procedure S0R42 'Schedule Satellite' describe? "
    "Answer from the internal documentation and name the page."
)
_UNIFAI_RAG_QUESTION = os.getenv("UNIFAI_RAG_QUESTION") or (_TEKOS_RAG_QUESTION if AGENT in ("tekos", "arkos") else "")
_UNIFAI_RAG_EXPECT = os.getenv("UNIFAI_RAG_EXPECT", "S0R42" if AGENT in ("tekos", "arkos") else "")
# Tekos's retriever also searches the Red Hat documentation (WEB sources, knowledge.tech): a basic
# product question must be answered from it and cite it. Tekos only; override or disable
# (UNIFAI_RAG_WEB_QUESTION="") for another corpus.
_TEKOS_RAG_WEB_QUESTION = (
    "What is a namespace in OpenShift? Answer from the Red Hat documentation and cite the source URL."
)
_UNIFAI_RAG_WEB_QUESTION = os.getenv(
    "UNIFAI_RAG_WEB_QUESTION", _TEKOS_RAG_WEB_QUESTION if AGENT == "tekos" else ""
)
_UNIFAI_RAG_WEB_EXPECT = os.getenv("UNIFAI_RAG_WEB_EXPECT", "docs.redhat.com")
# A member of the agent's knowledge groups (override with UNIFAI_RAG_PERSONA).
_UNIFAI_RAG_PERSONAS = {
    "tekos": "consultant-01", "arkos": "consultant-01", "comage": "sale-01", "advantage": "adv-01", "finage": "finance-01",
}


def u_rag_retrieval(s: Dict[str, Any]) -> ScenarioResult:
    """The RAG scenario through UnifAI: a member of the source's groups gets an answer that
    went through the retriever (and names the page when one is expected). The whole path
    (retriever, forwarded token, ACL) is exercised, not just the search service."""
    persona = os.getenv("UNIFAI_RAG_PERSONA") or _UNIFAI_RAG_PERSONAS.get(AGENT) or s.get("persona", "consultant-01")
    question = _UNIFAI_RAG_QUESTION or s.get("query", "")
    try:
        run_ = _unifai().collect(persona, question, deadline_seconds=170)
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    tools, reply = run_["tools"], run_["reply"]
    names_page = (_UNIFAI_RAG_EXPECT in reply) if _UNIFAI_RAG_EXPECT else bool(reply)
    # With retrieve_first the node retrieves before the model reasons: no tool event is emitted, so a page
    # only the sources can name (UNIFAI_RAG_EXPECT) is the proof of retrieval. Without an expected page,
    # the retriever tool call is still required.
    used_retriever = any("retriever" in t for t in tools)
    ok = names_page if _UNIFAI_RAG_EXPECT else (used_retriever and names_page)
    detail = f"tool_calls={tools} names_page={names_page}"
    if _UNIFAI_RAG_WEB_QUESTION:
        # Second leg: the same retriever over the Red Hat documentation. The answer must cite it.
        try:
            web = _unifai().collect(persona, _UNIFAI_RAG_WEB_QUESTION, deadline_seconds=170)
            cites_docs = _UNIFAI_RAG_WEB_EXPECT in web["reply"]
        except Exception as exc:  # noqa: BLE001
            cites_docs = False
            detail += f" web_error={exc}"
        ok = ok and cites_docs
        detail += f" cites_red_hat_docs={cites_docs}"
    return ScenarioResult(s["id"], s["title"], ok, detail)


def u_rag_retrieval_executed(s: Dict[str, Any]) -> ScenarioResult:
    """The retrieval ran before the model, proven by the trace (WP-155, comage scenario 11).

    An agent with retrieve_first retrieves before the model reasons, so no tool event exists, and an
    agent with no indexed corpus for its topic has no page to cite. What can be proven is that the
    retrieval executed: the run's trace carries at least one `rag.search` span (Tempo, `TEMPO_URL`).
    Without `TEMPO_URL` the scenario is skipped, never passed. A citation needs a corpus for the
    topic; the detail says how many results the searches returned."""
    tempo = os.getenv("TEMPO_URL", "").strip()
    if not tempo:
        return _skip(s, "no trace backend (TEMPO_URL unset), retrieval cannot be observed")
    persona = os.getenv("UNIFAI_RAG_PERSONA") or _UNIFAI_RAG_PERSONAS.get(AGENT) or s.get("persona", "consultant-01")
    question = _UNIFAI_RAG_QUESTION or s.get("query", "")
    try:
        run_ = _unifai().collect(persona, question, deadline_seconds=170)
    except Exception as exc:  # noqa: BLE001
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    run_id = run_.get("session_id", "")
    if not run_id:
        return ScenarioResult(s["id"], s["title"], False, "the turn produced no session id")
    try:
        searches = _unifai_tempo_rag_searches(run_id, tempo)
    except Exception as exc:  # noqa: BLE001 - an unreachable backend cannot prove anything
        return ScenarioResult(s["id"], s["title"], False, f"trace backend: {exc}")
    results = [x["results"] for x in searches]
    detail = f"rag.search spans={len(searches)} results={results} (no citation expected without a corpus for the topic)"
    return ScenarioResult(s["id"], s["title"], bool(searches) and bool(run_["reply"]), detail)


def u_chat_blocked_for_placeholder_agent(s: Dict[str, Any]) -> ScenarioResult:
    """ADR-0007 on UnifAI: a placeholder agent must not answer. Its workflow is not exposed to
    the persona; if it nevertheless is, a chat turn must not return a reply."""
    t = _unifai()
    names = t.visible_workflows(s["persona"])
    workflow = os.getenv("UNIFAI_WORKFLOW") or AGENT
    if workflow not in names:
        return ScenarioResult(s["id"], s["title"], True, f"no {workflow!r} workflow visible (visible={names})")
    try:
        first = t.run(s["persona"], s["message"], timeout=s.get("timeout_seconds", 60))
    except Exception as exc:  # noqa: BLE001 - a refused session is the expected outcome
        return ScenarioResult(s["id"], s["title"], True, f"refused: {exc}")
    return ScenarioResult(
        s["id"], s["title"], first.status != 200 or not first.reply, f"status={first.status} reply_len={len(first.reply)}"
    )


def u_chat_register_conformance(s: Dict[str, Any]) -> ScenarioResult:
    """ADR-0526 (WP-087): asserts HOW an answer is written, not what it says - the one
    tone-aware scenario (see evaluations/register_conformance.py's module docstring), scored
    by register_conformance.score_text over UnifAI turns.

    `expect_register: false` inverts it (rules 11-13: a technical answer must NOT be
    slangified). `samples` (default 1) fires the prompt that many times: rules 11-13 must
    hold on EVERY sample, the marker floor on at least one, and the `expect_register: false`
    ceiling on the mean density."""
    if _unifai_placeholder_skip(s):
        return _skip(s, _PLACEHOLDER_WHY)
    # This file runs under two layouts: evaluations/tekos/ in the repo (register_conformance.py
    # one level up) and flattened into /gate in the Jobs; cover both.
    _here = pathlib.Path(__file__).resolve().parent
    for candidate in (_here, _here.parent):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    import register_conformance

    timeout = s.get("timeout_seconds", 30)
    num_samples = int(s.get("samples", 1))
    scored: List[Dict[str, Any]] = []
    for i in range(num_samples):
        r = _unifai().run(s["persona"], s["message"], timeout=timeout)
        if r.status != 200:
            return ScenarioResult(s["id"], s["title"], False, f"status={r.status} (sample {i + 1}/{num_samples})")
        scored.append(register_conformance.score_text(r.reply))
    for sc in scored:
        if sc["violations"]:
            return ScenarioResult(
                s["id"], s["title"], False,
                "rules 11-13: " + "; ".join(f"{v['marker']} in {v['kind']}" for v in sc["violations"][:3]),
            )
    if s.get("expect_register", True):
        min_markers = int(s.get("min_markers", 1))
        best = max(scored, key=lambda sc: sc["marker_count"])
        hits = sum(1 for sc in scored if sc["marker_count"] >= min_markers)
        return ScenarioResult(
            s["id"], s["title"], hits > 0, f"samples={num_samples} hits={hits}/{num_samples} best_markers={best['marker_count']}"
        )
    max_density = float(s.get("max_density", 0.25))
    mean = sum(sc["density"] for sc in scored) / num_samples
    return ScenarioResult(s["id"], s["title"], mean <= max_density, f"samples={num_samples} mean_density={mean:.3f}")


def u_agent_isolation(s: Dict[str, Any]) -> ScenarioResult:
    try:
        import kubernetes  # noqa: F401
    except ImportError:
        return _skip(s, "needs the in-cluster Kubernetes client (runs in the Day 3 evaluation Job)")
    return agent_isolation_placeholder_empty(s)


def u_bff_rejects_missing_jwt(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(
        f"{_unifai().ui_url}/api2/sessions/user.session.create",
        json={"blueprintId": "x"},
        timeout=15,
        verify=False,
    )
    return ScenarioResult(s["id"], s["title"], resp.status_code == 401, f"status={resp.status_code}")


def u_bff_rejects_wrong_audience(s: Dict[str, Any]) -> ScenarioResult:
    return _skip(s, "UnifAI authenticates a server-side session cookie, it accepts no bearer token")


# The services a health_endpoints_all_ok scenario may name in its `services:`
# list; without one, every entry is checked.
def _health_urls() -> Dict[str, str]:
    return {
        "unifai-ui": f"{_unifai().ui_url}/",
        "mcp-gateway": f"{MCP_GATEWAY_URL}/healthz",
        "ai-gateway": f"{AI_GATEWAY_URL}/healthz",
    }


def u_health_endpoints_all_ok(s: Dict[str, Any]) -> ScenarioResult:
    urls = _health_urls()
    wanted = s.get("services") or list(urls)
    unknown = [svc for svc in wanted if svc not in urls]
    if unknown:
        return ScenarioResult(s["id"], s["title"], False, f"unknown services {unknown} (known: {sorted(urls)})")
    statuses: Dict[str, Any] = {}
    for name in wanted:
        try:
            statuses[name] = httpx.get(urls[name], timeout=10, verify=False).status_code
        except Exception as exc:  # noqa: BLE001
            statuses[name] = str(exc)
    return ScenarioResult(s["id"], s["title"], all(v == 200 for v in statuses.values()), json.dumps(statuses))


HANDLERS: Dict[str, Callable[[Dict[str, Any]], ScenarioResult]] = {
    # Served by UnifAI (the `portal_*`/`bff_*` type names predate it and are
    # kept so every agent's scenarios.yaml stays unchanged).
    "portal_lists_all_agents": u_portal_lists_all_agents,
    "portal_requires_login": u_portal_requires_login,
    "portal_tile_state": u_portal_tile_state,
    "chat_basic_qa": u_chat_basic_qa,
    "chat_first_token_latency": u_chat_first_token_latency,
    "chat_streaming_sse": u_chat_streaming,
    "chat_triggers_tool": u_chat_triggers_tool,
    "rag_retrieval_has_citation": u_rag_retrieval,
    "rag_retrieval_executed": u_rag_retrieval_executed,
    "chat_blocked_for_placeholder_agent": u_chat_blocked_for_placeholder_agent,
    # ADR-0526 (WP-087): only the agents whose scenarios.yaml declares the
    # type actually run it.
    "chat_register_conformance": u_chat_register_conformance,
    "bff_rejects_missing_jwt": u_bff_rejects_missing_jwt,
    "bff_rejects_wrong_audience": u_bff_rejects_wrong_audience,
    "agent_isolation_placeholder_empty": u_agent_isolation,
    "health_endpoints_all_ok": u_health_endpoints_all_ok,
    # Shared platform services, called directly.
    "keycloak_login": keycloak_login,
    "mcp_gateway_denied": mcp_gateway_denied,
    "mcp_gateway_unknown_tool": mcp_gateway_unknown_tool,
    "model_router_fails_closed": model_router_fails_closed,
    "model_router_prefers_local": model_router_prefers_local,
}


def run() -> List[ScenarioResult]:
    # Resolved via AGENT, not this file's own directory: a wrapper agent
    # (e.g. evaluations/arkos/run_scenarios.py) delegates to this exact
    # function after setting AGENT, and its scenarios.yaml lives in ITS
    # OWN directory (evaluations/<AGENT>/), not wherever this canonical
    # implementation happens to be physically checked in.
    scenarios_path = pathlib.Path(__file__).resolve().parent.parent / AGENT / "scenarios.yaml"
    scenarios = yaml.safe_load(scenarios_path.read_text())["scenarios"]

    results: List[ScenarioResult] = []
    for s in scenarios:
        handler = HANDLERS.get(s["type"])
        if handler is None:
            result = ScenarioResult(s["id"], s["title"], False, f"no handler for type '{s['type']}'")
        else:
            try:
                result = handler(s)
            except Exception as exc:  # noqa: BLE001 - a scenario erroring is a fail, not a crash
                result = ScenarioResult(s["id"], s["title"], False, f"unhandled error: {exc}")
        results.append(result)
        log_test_line(AGENT, "scenario", str(result.id), result.title, result.passed, result.detail)
    return results


def main() -> int:
    results = run()

    skipped = [r for r in results if r.skipped]
    results = [r for r in results if not r.skipped]
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    rate = passed / total if total else 0.0

    print(f"target: {TARGET}")
    print(f"{'ID':<4}{'PASS':<6}{'TITLE'}")
    for r in results:
        print(f"{r.id:<4}{'✓' if r.passed else '✗':<6}{r.title}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")
    for r in skipped:
        print(f"{r.id:<4}{'-':<6}{r.title}\n      -> {r.detail}")

    threshold = 0.75
    print(f"\n{passed}/{total} passed ({rate:.0%}) - threshold {threshold:.0%} (ADR-0028)"
          + (f", {len(skipped)} skipped (not applicable on UnifAI)" if skipped else ""))

    # Only reached for a standalone `python3 run_scenarios.py` invocation -
    # when imported by platform/testing/day2_stresstest.py (the Job's real
    # entrypoint), this main() never runs; that orchestrator cleans up the
    # shared UnifaiTarget's sessions itself, once, after every layer has run.
    # Deletes exactly the UnifAI sessions this run created, never a sweep of
    # the persona's sessions (the personas also serve live human demos).
    if _unifai_target is None:
        print("cleanup: no UnifAI session was created")
    elif os.getenv("CLEANUP_TEST_DATA", "1") != "0":
        deleted, failed = _unifai_target.cleanup()
        print(f"cleanup: {deleted} conversation(s) removed, {failed} failed")
    else:
        print("cleanup: skipped (CLEANUP_TEST_DATA=0), the UnifAI sessions this run created are left in place")

    if rate >= threshold:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

