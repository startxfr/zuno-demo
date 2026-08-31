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

This cannot be executed in the sandbox this repo was built in (no live
cluster) - it is written to be genuinely runnable once one exists, not a
mock. Each `type` in scenarios.yaml maps to exactly one handler function
below; add a new scenario by adding a YAML entry plus (if it's a new type)
a handler.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

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

# ADR-0342/WP-31: which agent this run evaluates - drives the frontend/BFF
# hostnames, the OIDC client id, and (via TASK_NAME below) which OKF task
# name is declared to the MCP Gateway. Defaults to "tekos" so every
# existing direct invocation of this file (`cd evaluations/tekos &&
# python3 run_scenarios.py`, with no AGENT set) behaves exactly as before
# this parameterization.
AGENT = os.getenv("AGENT", "tekos")
# The OKF task this agent's evaluation exercises (app/registry.py's
# TaskDefinition.name) - required by _invoke_tool's X-Zuno-Task header
# (ADR-0036). Each agent's own README documents its value; defaulting to
# Tekos's real task name keeps the unparameterized case unchanged.
TASK_NAME = os.getenv("TASK_NAME", "answer-technical-question")

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://keycloak.apps.mycluster.example.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", f"https://{AGENT}.apps.mycluster.example.com")
BFF_URL = os.getenv("BFF_URL", f"http://{AGENT}-bff.zuno-ai-run.svc.cluster.local:8080")
# Agent Runtime and every platform service below are shared across every
# agent (ADR-0342's generic dispatch, ADR-0009's split services) - never
# agent-specific, unlike FRONTEND_URL/BFF_URL above.
RUNTIME_URL = os.getenv("RUNTIME_URL", "http://agent-runtime.zuno-ai-run.svc.cluster.local:8080")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai-run.svc.cluster.local:8080")
RAG_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc.cluster.local:8080")
# ADR-0326/WP-33: Comage's own live MCP server (evaluations/comage's
# scenario 20 includes it in `services:`; harmless to resolve unconditionally
# for every agent).
SALESFORCE_MCP_URL = os.getenv("SALESFORCE_MCP_URL", "http://salesforce-mcp.zuno-ai-run.svc.cluster.local:8000")

REALM = "zuno"
# Shared demo-persona password (ADR-0041) - never hardcoded; read from the
# same place `make configure keycloak` puts it (an operator running this
# script fetches it once, e.g.
# `vault kv get -field=password secret/zuno/keycloak/demo-personas`).
# ansible/roles/keycloak/README.md's "Two integration fixes" note explains
# why every fixture user's credential is non-temporary.
DEMO_PASSWORD = os.getenv("DEMO_PERSONA_PASSWORD")
# Confidential client's own secret - never hardcoded; read from the same
# place `make configure keycloak` puts it (an operator running this script
# fetches it once, e.g. `vault kv get -field=client_secret secret/zuno/keycloak/<agent>-frontend`).
# Named after AGENT (TEKOS_FRONTEND_CLIENT_SECRET when unset, matching this
# module's original single env var exactly).
FRONTEND_CLIENT_SECRET = os.getenv(f"{AGENT.upper()}_FRONTEND_CLIENT_SECRET")

SERVICE_HEALTH_URLS = {
    "frontend": f"{FRONTEND_URL}/healthz",
    "bff": f"{BFF_URL}/healthz",
    "agent-runtime": f"{RUNTIME_URL}/healthz",
    "mcp-gateway": f"{MCP_GATEWAY_URL}/healthz",
    "rag-service": f"{RAG_URL}/healthz",
    "salesforce-mcp": f"{SALESFORCE_MCP_URL}/healthz",
}


@dataclass
class ScenarioResult:
    id: int
    title: str
    passed: bool
    detail: str = ""


_token_cache: Dict[str, str] = {}


def get_token(persona: str) -> str:
    """Resource Owner Password Credentials grant against AGENT's own
    confidential frontend client - appropriate for an automated evaluation
    harness acting on behalf of fixture personas, not for real user login
    (which uses the authorization-code flow, see components/agent-frontend).
    """
    if persona in _token_cache:
        return _token_cache[persona]
    if not FRONTEND_CLIENT_SECRET:
        raise RuntimeError(f"{AGENT.upper()}_FRONTEND_CLIENT_SECRET is required to obtain persona tokens")
    if not DEMO_PASSWORD:
        raise RuntimeError("DEMO_PERSONA_PASSWORD is required to obtain persona tokens")

    resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": f"{AGENT}-frontend",
            "client_secret": FRONTEND_CLIENT_SECRET,
            "username": persona,
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
# Test-generated conversation cleanup. Every chat call below creates a
# brand-new, permanently-persisted conversation (agent-runtime's
# _resolve_run_id mints a fresh run_id whenever the caller doesn't already
# have one to resume - there is no way to pre-tag a new conversation's
# identity, and session_id is never written to any database column, only
# carried into AgentState.session_id for tracing). Since these scripts
# authenticate as real demo personas that are also used for live human
# demos, an uncleaned run leaves synthetic conversations
# ("Can you generate a mockup image...", etc.) sitting in that persona's
# real conversation list.
#
# Rather than a heuristic sweep (by time window or persona, both of which
# risk deleting a real demo's conversation happening concurrently), this
# records the exact run_id every call creates and hard-deletes exactly
# those at the end of the run via DELETE .../runs/{run_id}/hard-delete
# (ADR-0515, already live - WP-066) - the same ownership check (owner_sub
# must match the caller) that endpoint already enforces, so this can never
# touch a conversation it didn't itself just create.
# --------------------------------------------------------------------------

_CREATED_RUN_IDS: List[Tuple[str, str]] = []  # (persona, run_id)


def record_run_id(persona: str, body: Dict[str, Any]) -> None:
    run_id = body.get("run_id")
    if run_id:
        _CREATED_RUN_IDS.append((persona, run_id))


def cleanup_created_runs() -> Tuple[int, int]:
    """Best-effort: a 404 (already gone) or any transport error is counted
    as failed but never raised - cleanup must never fail an otherwise-
    passing test run. Always targets RUNTIME_URL directly regardless of
    whether the conversation was created via BFF_URL or RUNTIME_URL - the
    backing conversations/checkpoint store is the same either way, and
    hard-delete is agent-runtime's own endpoint."""
    deleted = failed = 0
    for persona, run_id in _CREATED_RUN_IDS:
        try:
            resp = httpx.delete(
                f"{RUNTIME_URL}/v1/agents/{AGENT}/runs/{run_id}/hard-delete",
                headers=auth_headers(persona),
                timeout=15,
            )
            if resp.status_code in (200, 404):
                deleted += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    _CREATED_RUN_IDS.clear()
    return deleted, failed


# ADR-0042: agent-frontend's `/` is a thin, always-200 HTML shell
# (internal/portal/portal.go) - it never redirects server-side and never
# reads an Authorization header. Sign-in state lives entirely in the
# server-rendered `#zuno-config` JSON blob (`signedIn`, and each tile's
# `clickable`), which the React SPA reads client-side. Both scenario
# handlers below that need to know sign-in state parse this blob instead
# of relying on HTTP status/headers or a Bearer token the frontend would
# never look at.
_ZUNO_CONFIG_RE = re.compile(r'<script id="zuno-config"[^>]*>(.*?)</script>', re.DOTALL)


def _zuno_config(body: str) -> Dict[str, Any]:
    match = _ZUNO_CONFIG_RE.search(body)
    if not match:
        raise RuntimeError("portal HTML has no #zuno-config script block")
    return json.loads(match.group(1))


_session_clients: Dict[str, httpx.Client] = {}


def get_session_client(persona: str) -> httpx.Client:
    """Completes the real browser OIDC flow - GET {FRONTEND_URL}/login
    (redirects to Keycloak's authorize endpoint), parse and submit
    Keycloak's own login form, follow the redirect back through
    /callback - and returns an httpx.Client whose cookie jar now carries
    the resulting `zuno_session` cookie, the only credential
    agent-frontend's `/` ever reads (ADR-0042). Distinct from
    get_token()/auth_headers() above, which mint a Bearer JWT for calling
    the BFF/Agent Runtime/MCP Gateway APIs directly - agent-frontend's
    browser-facing routes are cookie-only and never accept that token.
    """
    if persona in _session_clients:
        return _session_clients[persona]
    if not DEMO_PASSWORD:
        raise RuntimeError("DEMO_PERSONA_PASSWORD is required to obtain a session cookie")

    client = httpx.Client(follow_redirects=True, timeout=15)
    login_page = client.get(f"{FRONTEND_URL}/login")
    login_page.raise_for_status()

    match = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', login_page.text)
    if not match:
        client.close()
        raise RuntimeError("could not find Keycloak's kc-form-login action URL")
    action_url = html.unescape(match.group(1))

    result = client.post(action_url, data={"username": persona, "password": DEMO_PASSWORD, "credentialId": ""})
    result.raise_for_status()
    if "zuno_session" not in client.cookies:
        client.close()
        raise RuntimeError(f"OIDC login for {persona!r} did not yield a zuno_session cookie (landed on {result.url})")

    _session_clients[persona] = client
    return client


# --------------------------------------------------------------------------
# Scenario handlers - one per `type` in scenarios.yaml
# --------------------------------------------------------------------------


def portal_lists_all_agents(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.get(FRONTEND_URL, headers=auth_headers(s["persona"]), timeout=10, follow_redirects=True)
    body = resp.text
    # naveo: sixth agent (ADR-0410/WP-41b); soursage/cognos: ADR-0349 §6
    # placeholder tiles - the portal auto-discovers tiles from the OKF
    # bundles baked into the frontend image, so this list only needs each
    # agent slug, no frontend code change.
    agents = ["comage", "tekos", "advantage", "finage", "arkos", "naveo", "soursage", "cognos"]
    missing = [a for a in agents if a not in body.lower()]
    return ScenarioResult(s["id"], s["title"], resp.status_code == 200 and not missing,
                           f"status={resp.status_code} missing_tiles={missing}")


def portal_requires_login(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.get(FRONTEND_URL, timeout=10, follow_redirects=True)
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    try:
        cfg = _zuno_config(resp.text)
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    any_clickable = any(t.get("clickable") for t in cfg.get("tiles", []))
    ok = cfg.get("signedIn") is False and not any_clickable
    return ScenarioResult(s["id"], s["title"], ok, f"signedIn={cfg.get('signedIn')} any_clickable={any_clickable}")


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
    downstream authorization decision (BFF, MCP Gateway) depends on -
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


def portal_tile_state(s: Dict[str, Any]) -> ScenarioResult:
    # Uses a real zuno_session cookie (get_session_client), not a Bearer
    # header - agent-frontend's `/` only ever reads the cookie (ADR-0042),
    # and reads the tile's own `clickable` field from #zuno-config rather
    # than sniffing "disabled"/"coming soon" text near the agent's name in
    # the HTML (fragile, and no longer even meaningful now the tile grid
    # is a client-side-rendered React component, not server-templated).
    try:
        client = get_session_client(s["persona"])
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    resp = client.get(FRONTEND_URL, timeout=10)
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    try:
        cfg = _zuno_config(resp.text)
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    agent = s["agent"]
    tile = next((t for t in cfg.get("tiles", []) if t.get("name") == agent), None)
    if tile is None:
        return ScenarioResult(s["id"], s["title"], False, f"tile for {agent} not found")
    enabled = bool(tile.get("clickable"))
    ok = enabled == s["expect_enabled"]
    return ScenarioResult(s["id"], s["title"], ok, f"enabled={enabled} expected={s['expect_enabled']}")


def chat_basic_qa(s: Dict[str, Any]) -> ScenarioResult:
    # timeout_seconds: most chat scenarios are interactive lookups (30s is
    # ample), but a handful (e.g. arkos's DAT drafting) structurally chain
    # multiple full-document LLM calls, `draft` forced onto a local model
    # with its own 60s-per-candidate timeout in ai-gateway - MEMORY.md
    # documents "long document workflows may take up to 10 minutes" as the
    # accepted SLO for exactly that shape. Per-scenario override, not a
    # blanket bump, so a genuinely-slow interactive reply still fails loud
    # at the default.
    timeout = s.get("timeout_seconds", 30)
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(s["persona"]),
        json={"session_id": "eval-7", "message": s["message"]},
        timeout=timeout,
    )
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    body = resp.json()
    record_run_id(s["persona"], body)
    ok = bool(body.get("reply")) and isinstance(body.get("citations", []), list)
    detail = f"reply_len={len(body.get('reply', ''))} citations={len(body.get('citations', []))}"

    # ADR-0215: a second turn on the SAME run_id must still succeed - the
    # live-path proof that resume + history-carrying actually works end to
    # end (components/agent-runtime/tests/test_history.py already covers
    # the exact prompt content this produces; a scripted smoke check with
    # no LLM judge can only assert the resumed turn completes with a
    # non-empty reply, not that it semantically recalled turn 1).
    follow_up = s.get("follow_up")
    run_id = body.get("run_id")
    if ok and follow_up and run_id:
        resp2 = httpx.post(
            f"{BFF_URL}/api/chat",
            headers=auth_headers(s["persona"]),
            json={"session_id": "eval-7", "message": follow_up, "run_id": run_id},
            timeout=timeout,
        )
        follow_up_ok = resp2.status_code == 200 and bool(resp2.json().get("reply"))
        ok = ok and follow_up_ok
        detail += f" follow_up_status={resp2.status_code} follow_up_ok={follow_up_ok}"

    return ScenarioResult(s["id"], s["title"], ok, detail)


def chat_first_token_latency(s: Dict[str, Any]) -> ScenarioResult:
    # Known, accepted gap in cleanup_created_runs()'s coverage: unlike
    # chat_streaming_sse below, this deliberately breaks on the very first
    # raw byte chunk to measure genuine first-byte latency - reading
    # further (or switching to iter_lines()) to extract the "start"
    # event's run_id would risk perturbing exactly the timing this
    # scenario exists to measure. Leaves at most one uncleaned test
    # conversation per run (this scenario, eval-9) rather than touch a
    # latency-sensitive SLO check.
    start = time.monotonic()
    first_byte_at: Optional[float] = None
    try:
        with httpx.stream(
            "POST",
            f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
            headers={**auth_headers(s["persona"]), "Accept": "text/event-stream"},
            json={"session_id": "eval-9", "user_sub": s["persona"], "message": s["message"]},
            timeout=30,
        ) as resp:
            for chunk in resp.iter_bytes():
                if chunk:
                    first_byte_at = time.monotonic()
                    break
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))

    if first_byte_at is None:
        return ScenarioResult(s["id"], s["title"], False, "no data received")
    elapsed = first_byte_at - start
    ok = elapsed <= s["max_seconds"]
    return ScenarioResult(s["id"], s["title"], ok, f"first_token_seconds={elapsed:.2f} max={s['max_seconds']}")


def chat_streaming_sse(s: Dict[str, Any]) -> ScenarioResult:
    saw_token, saw_done = False, False
    # main.py's _stream_chat always yields event "start" (carrying run_id)
    # first, before any "token"/"done" event - captured here purely for
    # cleanup_created_runs(), never used for this scenario's own pass/fail.
    expect_start_data = False
    # Same per-scenario override as chat_basic_qa's own timeout - was
    # hardcoded to 30 here regardless of the scenario's declared
    # timeout_seconds, so arkos's structure-demo streaming scenario (which
    # declares 180s for exactly this reason) always raced a client-side
    # timeout well before the BFF's own 180s streaming budget, surfacing as
    # a false "timed out" instead of exercising the real behavior.
    try:
        with httpx.stream(
            "POST",
            f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
            headers={**auth_headers(s["persona"]), "Accept": "text/event-stream"},
            json={"session_id": "eval-10", "user_sub": s["persona"], "message": s["message"]},
            timeout=s.get("timeout_seconds", 30),
        ) as resp:
            for line in resp.iter_lines():
                if expect_start_data and line.startswith("data:"):
                    try:
                        record_run_id(s["persona"], json.loads(line[len("data:"):].strip()))
                    except Exception:
                        pass
                    expect_start_data = False
                elif line.startswith("event: start"):
                    expect_start_data = True
                elif line.startswith("event: token"):
                    saw_token = True
                elif line.startswith("event: done"):
                    saw_done = True
                    break
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    ok = saw_token and saw_done
    return ScenarioResult(s["id"], s["title"], ok, f"saw_token={saw_token} saw_done={saw_done}")


def chat_triggers_tool(s: Dict[str, Any]) -> ScenarioResult:
    # timeout_seconds: see chat_basic_qa's own comment - same per-scenario
    # override for structurally-slow workflows (e.g. arkos's DAT drafting).
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
        headers=auth_headers(s["persona"]),
        json={"session_id": "eval-11", "user_sub": s["persona"], "message": s["message"]},
        timeout=s.get("timeout_seconds", 30),
    )
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    body = resp.json()
    record_run_id(s["persona"], body)
    # Citation.source is the raw result URL
    # (app/graph/nodes.py's respond_node: `item.get("url") or "live-read"`),
    # not a fixed marker string for the tool that produced it - Tekos's real
    # Confluence instance, for instance, is hosted at startxfr.atlassian.net,
    # which never contains the word "confluence". source_mode ("live"/"both"
    # only when a live tool call's results actually contributed - ADR-0205's
    # _compute_source_mode, agent-agnostic) is the correct, hosting-domain-
    # independent signal that THIS task's one declared live_read_tool
    # (Confluence for Tekos, Salesforce for Comage, ADR-0326/WP-33 - each
    # task has exactly one, so no ambiguity) fired and contributed, so check
    # that instead of pattern-matching the citation URL against a per-agent
    # marker string.
    ok = body.get("source_mode") in ("live", "both")
    return ScenarioResult(s["id"], s["title"], ok, f"source_mode={body.get('source_mode')} citations={body.get('citations', [])}")


def chat_blocked_for_placeholder_agent(s: Dict[str, Any]) -> ScenarioResult:
    """ADR-0007: agent-runtime's `_active_agent_or_404` (components/agent-runtime/app/main.py)
    rejects any agent whose OKF status isn't "active" before GraphFactory
    is ever consulted - by design, not a bug. For a placeholder-status
    agent, real chat can never succeed, so this proves the boundary holds
    rather than asserting a reply that will never come.

    via: "runtime" (default) calls RUNTIME_URL directly, unaffected by
    anything BFF-side, and gets a deterministic 404. via: "bff" calls
    BFF_URL instead, which independently forwards agent-runtime's 404
    once the caller's JWT clears agent-bff's own verification - but
    live-cluster-confirmed 2026-08-21: agent-bff's JWKS-fetch http.Client
    (components/agent-bff/internal/jwks/jwks.go) trusts only the default
    system CA store, not the cluster-internal CA that signs Keycloak's
    Route certificate, so a freshly-rolled agent-bff pod's first
    verification attempt can independently fail with its own 401 before
    ever reaching agent-runtime's check - a second, real, unrelated bug.
    Either response proves the same thing a real caller cares about (no
    chat reply was produced), so the "bff" path only asserts != 200
    rather than pinning the exact code.
    """
    via = s.get("via", "runtime")
    if via == "bff":
        resp = httpx.post(
            f"{BFF_URL}/api/chat",
            headers=auth_headers(s["persona"]),
            json={"session_id": "eval-7", "message": s["message"]},
            timeout=30,
        )
        ok = resp.status_code != 200
    else:
        resp = httpx.post(
            f"{RUNTIME_URL}/v1/agents/{AGENT}/chat",
            headers=auth_headers(s["persona"]),
            json={"session_id": "eval-11", "user_sub": s["persona"], "message": s["message"]},
            timeout=30,
        )
        ok = resp.status_code == 404
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code} via={via}")


def rag_retrieval_has_citation(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(f"{RAG_URL}/v1/search", json={"query": s["query"], "top_k": 5}, timeout=15)
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    results = resp.json().get("results", [])
    return ScenarioResult(s["id"], s["title"], len(results) > 0, f"result_count={len(results)}")


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
    # No HTTP surface exposes ModelRouter directly; exercised indirectly via
    # a chat request declared at the target classification once agent-runtime
    # accepts a classification override, or verified by code review of
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


def bff_rejects_missing_jwt(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(f"{BFF_URL}/api/chat", json={"message": "hello"}, timeout=10)
    ok = resp.status_code == 401
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code}")


def bff_rejects_wrong_audience(s: Dict[str, Any]) -> ScenarioResult:
    # Any non-AGENT-frontend-audience token would do; this evaluation
    # harness only ever authenticates through AGENT's own confidential
    # client (see get_token() above), so this exercises the audience check
    # with a deliberately malformed/foreign token instead of a same-realm
    # token carrying a different agent's audience.
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"message": "hello"},
        timeout=10,
    )
    ok = resp.status_code == 401
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code}")


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


def health_endpoints_all_ok(s: Dict[str, Any]) -> ScenarioResult:
    statuses = {}
    for svc in s["services"]:
        url = SERVICE_HEALTH_URLS[svc]
        try:
            resp = httpx.get(url, timeout=10)
            statuses[svc] = resp.status_code
        except Exception as exc:
            statuses[svc] = str(exc)
    ok = all(v == 200 for v in statuses.values())
    return ScenarioResult(s["id"], s["title"], ok, json.dumps(statuses))


def chat_register_conformance(s: Dict[str, Any]) -> ScenarioResult:
    """ADR-0526 (WP-087): asserts HOW an answer is written, not what it says.

    The one tone-aware check in this file. Every other scenario here is
    deliberately tone-blind (status codes, JSON shape, non-emptiness,
    latency, SSE framing), which is what makes the acceptance suite a clean
    substance control for the register variant - see
    evaluations/register_conformance.py's module docstring.

    This is the POST-PROMOTION live check. It is NOT what gates the
    pipeline: components/mlops's evaluate stage scores train-lora's
    held-out completions offline, because the merged model is deployed
    nowhere at gate time. Two checks, one scorer, no duplicated thresholds.

    `expect_register: false` inverts it, which is how rules 11-13 get
    asserted live: a technical question whose answer must NOT be slangified.
    """
    # Imported here, not at module scope, and with an explicit path setup:
    # this file runs under TWO different layouts. In the repo it sits at
    # evaluations/tekos/, with register_conformance.py one level up; in the
    # acceptance-gate Job every script is flattened into /gate as sibling
    # files. Covering both is two sys.path entries, and getting it wrong is
    # an ImportError inside a live gate run.
    _here = pathlib.Path(__file__).resolve().parent
    for candidate in (_here, _here.parent):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    import register_conformance

    timeout = s.get("timeout_seconds", 30)
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(s["persona"]),
        json={"session_id": "eval-register", "message": s["message"]},
        timeout=timeout,
    )
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    body = resp.json()
    record_run_id(s["persona"], body)
    reply = body.get("reply") or ""
    scored = register_conformance.score_text(reply)

    # Rules 11-13 are asserted on EVERY register scenario, not only the
    # negative one: slangified syntax is a failure whatever the question.
    if scored["violations"]:
        return ScenarioResult(
            s["id"], s["title"], False,
            "rules 11-13: " + "; ".join(f"{v['marker']} in {v['kind']}" for v in scored["violations"][:3]),
        )
    if s.get("expect_register", True):
        ok = scored["marker_count"] >= int(s.get("min_markers", 1))
    else:
        # A technical answer may still carry register - rule 18 says
        # professional topics use MEDIUM familiarity, not none - so this
        # asserts a ceiling, never zero.
        ok = scored["density"] <= float(s.get("max_density", 0.25))
    return ScenarioResult(
        s["id"], s["title"], ok,
        f"markers={scored['marker_count']} density={scored['density']:.3f} "
        f"found={','.join(scored['markers'][:6])} reply_len={len(reply)}",
    )


HANDLERS: Dict[str, Callable[[Dict[str, Any]], ScenarioResult]] = {
    "portal_lists_all_agents": portal_lists_all_agents,
    "portal_requires_login": portal_requires_login,
    "keycloak_login": keycloak_login,
    "portal_tile_state": portal_tile_state,
    "chat_basic_qa": chat_basic_qa,
    "chat_first_token_latency": chat_first_token_latency,
    "chat_streaming_sse": chat_streaming_sse,
    "chat_triggers_tool": chat_triggers_tool,
    # ADR-0526 (WP-087). Added to the SHARED dict, so all six agents get it
    # from this one entry - only the agents whose scenarios.yaml declares
    # the type actually run it.
    "chat_register_conformance": chat_register_conformance,
    "chat_blocked_for_placeholder_agent": chat_blocked_for_placeholder_agent,
    "rag_retrieval_has_citation": rag_retrieval_has_citation,
    "mcp_gateway_denied": mcp_gateway_denied,
    "mcp_gateway_unknown_tool": mcp_gateway_unknown_tool,
    "model_router_fails_closed": model_router_fails_closed,
    "model_router_prefers_local": model_router_prefers_local,
    "bff_rejects_missing_jwt": bff_rejects_missing_jwt,
    "bff_rejects_wrong_audience": bff_rejects_wrong_audience,
    "agent_isolation_placeholder_empty": agent_isolation_placeholder_empty,
    "health_endpoints_all_ok": health_endpoints_all_ok,
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

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    rate = passed / total if total else 0.0

    print(f"{'ID':<4}{'PASS':<6}{'TITLE'}")
    for r in results:
        print(f"{r.id:<4}{'✓' if r.passed else '✗':<6}{r.title}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    threshold = 0.75
    print(f"\n{passed}/{total} passed ({rate:.0%}) - threshold {threshold:.0%} (ADR-0028)")

    # Only reached for a standalone `python3 run_scenarios.py` invocation -
    # when imported by platform/testing/day2_stresstest.py (the Job's real
    # entrypoint), this main() never runs; that orchestrator calls
    # cleanup_created_runs() itself once, after every layer (scenario,
    # security, stress_test) has had a chance to add to the same shared
    # _CREATED_RUN_IDS list.
    if os.getenv("CLEANUP_TEST_DATA", "1") != "0":
        deleted, failed = cleanup_created_runs()
        print(f"cleanup: {deleted} conversation(s) removed, {failed} failed")
    else:
        print(f"cleanup: skipped (CLEANUP_TEST_DATA=0), {len(_CREATED_RUN_IDS)} conversation(s) left in place")

    if rate >= threshold:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
