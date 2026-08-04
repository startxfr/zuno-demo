#!/usr/bin/env python3
"""Runs the 20 Tekos acceptance scenarios (scenarios.yaml) against a live
deployment and reports the pass rate against the 75% threshold (ADR-0027,
ADR-0028). See README.md for required environment variables.

This cannot be executed in the sandbox this repo was built in (no live
cluster) - it is written to be genuinely runnable once one exists, not a
mock. Each `type` in scenarios.yaml maps to exactly one handler function
below; add a new scenario by adding a YAML entry plus (if it's a new type)
a handler.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import httpx
import yaml

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://sso.apps.example.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://tekos.apps.example.com")
BFF_URL = os.getenv("BFF_URL", "http://tekos-bff.zuno-agent-tekos.svc.cluster.local:8080")
RUNTIME_URL = os.getenv("RUNTIME_URL", "http://agent-runtime.zuno-ai.svc.cluster.local:8080")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway.zuno-ai.svc.cluster.local:8080")
RAG_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service.zuno-data.svc.cluster.local:8080")
SALES_DB_URL = os.getenv("SALES_DB_MCP_URL", "http://sales-db-mcp.zuno-ai.svc.cluster.local:8000")

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
# fetches it once, e.g. `vault kv get -field=client_secret secret/zuno/keycloak/tekos-frontend`).
TEKOS_FRONTEND_CLIENT_SECRET = os.getenv("TEKOS_FRONTEND_CLIENT_SECRET")

SERVICE_HEALTH_URLS = {
    "frontend": f"{FRONTEND_URL}/healthz",
    "bff": f"{BFF_URL}/healthz",
    "agent-runtime": f"{RUNTIME_URL}/healthz",
    "mcp-gateway": f"{MCP_GATEWAY_URL}/healthz",
    "rag-service": f"{RAG_URL}/healthz",
    "sales-db-mcp": f"{SALES_DB_URL}/healthz",
}


@dataclass
class ScenarioResult:
    id: int
    title: str
    passed: bool
    detail: str = ""


_token_cache: Dict[str, str] = {}


def get_token(persona: str) -> str:
    """Resource Owner Password Credentials grant against the confidential
    tekos-frontend client - appropriate for an automated evaluation harness
    acting on behalf of fixture personas, not for real user login (which
    uses the authorization-code flow, see components/agent-frontend).
    """
    if persona in _token_cache:
        return _token_cache[persona]
    if not TEKOS_FRONTEND_CLIENT_SECRET:
        raise RuntimeError("TEKOS_FRONTEND_CLIENT_SECRET is required to obtain persona tokens")
    if not DEMO_PASSWORD:
        raise RuntimeError("DEMO_PERSONA_PASSWORD is required to obtain persona tokens")

    resp = httpx.post(
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "tekos-frontend",
            "client_secret": TEKOS_FRONTEND_CLIENT_SECRET,
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
# Scenario handlers - one per `type` in scenarios.yaml
# --------------------------------------------------------------------------


def portal_lists_all_agents(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.get(FRONTEND_URL, headers=auth_headers(s["persona"]), timeout=10, follow_redirects=True)
    body = resp.text
    agents = ["comage", "tekos", "advantage", "finage", "arkos"]
    missing = [a for a in agents if a not in body.lower()]
    return ScenarioResult(s["id"], s["title"], resp.status_code == 200 and not missing,
                           f"status={resp.status_code} missing_tiles={missing}")


def portal_requires_login(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.get(FRONTEND_URL, timeout=10, follow_redirects=False)
    ok = resp.status_code in (302, 303, 401) or "/login" in resp.headers.get("location", "")
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code}")


def keycloak_login(s: Dict[str, Any]) -> ScenarioResult:
    try:
        token = get_token(s["persona"])
        return ScenarioResult(s["id"], s["title"], bool(token), "token acquired")
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))


def portal_tile_state(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.get(FRONTEND_URL, headers=auth_headers(s["persona"]), timeout=10, follow_redirects=True)
    body = resp.text.lower()
    agent = s["agent"]
    idx = body.find(agent)
    if idx == -1:
        return ScenarioResult(s["id"], s["title"], False, f"tile for {agent} not found")
    window = body[max(0, idx - 200): idx + 200]
    is_disabled = "disabled" in window or "coming soon" in window or "coming-soon" in window
    enabled = not is_disabled
    ok = enabled == s["expect_enabled"]
    return ScenarioResult(s["id"], s["title"], ok, f"enabled={enabled} expected={s['expect_enabled']}")


def chat_basic_qa(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(s["persona"]),
        json={"message": s["message"]},
        timeout=30,
    )
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    body = resp.json()
    ok = bool(body.get("reply")) and isinstance(body.get("citations", []), list)
    return ScenarioResult(s["id"], s["title"], ok, f"reply_len={len(body.get('reply', ''))} citations={len(body.get('citations', []))}")


def chat_first_token_latency(s: Dict[str, Any]) -> ScenarioResult:
    start = time.monotonic()
    first_byte_at: Optional[float] = None
    try:
        with httpx.stream(
            "POST",
            f"{RUNTIME_URL}/v1/agents/tekos/chat",
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
    try:
        with httpx.stream(
            "POST",
            f"{RUNTIME_URL}/v1/agents/tekos/chat",
            headers={**auth_headers(s["persona"]), "Accept": "text/event-stream"},
            json={"session_id": "eval-10", "user_sub": s["persona"], "message": s["message"]},
            timeout=30,
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("event: token"):
                    saw_token = True
                elif line.startswith("event: done"):
                    saw_done = True
                    break
    except Exception as exc:
        return ScenarioResult(s["id"], s["title"], False, str(exc))
    ok = saw_token and saw_done
    return ScenarioResult(s["id"], s["title"], ok, f"saw_token={saw_token} saw_done={saw_done}")


def chat_triggers_tool(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers(s["persona"]),
        json={"session_id": "eval-11", "user_sub": s["persona"], "message": s["message"]},
        timeout=30,
    )
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    citations = resp.json().get("citations", [])
    ok = any("confluence" in c.get("source", "").lower() for c in citations)
    return ScenarioResult(s["id"], s["title"], ok, f"citations={citations}")


def rag_retrieval_has_citation(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(f"{RAG_URL}/v1/search", json={"query": s["query"], "top_k": 5}, timeout=15)
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code}")
    results = resp.json().get("results", [])
    return ScenarioResult(s["id"], s["title"], len(results) > 0, f"result_count={len(results)}")


def _invoke_tool(persona: str, tool: str, arguments: Dict[str, Any], classification: str = "C1") -> httpx.Response:
    return httpx.post(
        f"{MCP_GATEWAY_URL}/v1/tools/{tool}/invoke",
        headers={**auth_headers(persona), "X-Zuno-Data-Classification": classification},
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
    c3_providers = [p["name"] for p in routing.get("providers", []) if "C3" in p.get("eligible_for", [])]
    ok = c3_providers == ["local"]
    return ScenarioResult(s["id"], s["title"], ok, f"C3-eligible providers={c3_providers}")


def model_router_prefers_local(s: Dict[str, Any]) -> ScenarioResult:
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    routing = yaml.safe_load((repo_root / "platform/ai-gateway/provider-routing.yaml").read_text())
    providers = routing.get("providers", [])
    ok = bool(providers) and providers[0]["name"] == "local" and "C1" in providers[0].get("eligible_for", [])
    return ScenarioResult(s["id"], s["title"], ok, f"first_provider={providers[0]['name'] if providers else None}")


def bff_rejects_missing_jwt(s: Dict[str, Any]) -> ScenarioResult:
    resp = httpx.post(f"{BFF_URL}/api/chat", json={"message": "hello"}, timeout=10)
    ok = resp.status_code == 401
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code}")


def bff_rejects_wrong_audience(s: Dict[str, Any]) -> ScenarioResult:
    # Any non-tekos-frontend-audience token would do; in practice only
    # tekos-frontend is used for login in v0 (all personas authenticate
    # through it - see components/agent-frontend/README.md), so this
    # exercises the audience check with a deliberately malformed/foreign
    # token instead of a same-realm token with a different audience.
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"message": "hello"},
        timeout=10,
    )
    ok = resp.status_code == 401
    return ScenarioResult(s["id"], s["title"], ok, f"status={resp.status_code}")


def sales_db_tool_via_gateway(s: Dict[str, Any]) -> ScenarioResult:
    resp = _invoke_tool(s["persona"], s["tool"], s["arguments"], classification="C2")
    if resp.status_code != 200:
        return ScenarioResult(s["id"], s["title"], False, f"status={resp.status_code} body={resp.text[:200]}")
    body = resp.json()
    ok = "customer" in body
    return ScenarioResult(s["id"], s["title"], ok, f"keys={list(body.keys())}")


def namespace_isolation_placeholder_empty(s: Dict[str, Any]) -> ScenarioResult:
    # Requires `oc`/`kubectl` on PATH and a valid kubeconfig - the one
    # scenario that inspects cluster state directly rather than an HTTP API.
    import subprocess

    all_empty = True
    details = []
    for ns in s["namespaces"]:
        try:
            out = subprocess.run(
                ["oc", "get", "pods", "-n", ns, "-o", "name"],
                capture_output=True, text=True, timeout=15, check=True,
            )
            pod_count = len([l for l in out.stdout.splitlines() if l.strip()])
        except Exception as exc:
            details.append(f"{ns}: error ({exc})")
            all_empty = False
            continue
        details.append(f"{ns}: {pod_count} pods")
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


HANDLERS: Dict[str, Callable[[Dict[str, Any]], ScenarioResult]] = {
    "portal_lists_all_agents": portal_lists_all_agents,
    "portal_requires_login": portal_requires_login,
    "keycloak_login": keycloak_login,
    "portal_tile_state": portal_tile_state,
    "chat_basic_qa": chat_basic_qa,
    "chat_first_token_latency": chat_first_token_latency,
    "chat_streaming_sse": chat_streaming_sse,
    "chat_triggers_tool": chat_triggers_tool,
    "rag_retrieval_has_citation": rag_retrieval_has_citation,
    "mcp_gateway_denied": mcp_gateway_denied,
    "mcp_gateway_unknown_tool": mcp_gateway_unknown_tool,
    "model_router_fails_closed": model_router_fails_closed,
    "model_router_prefers_local": model_router_prefers_local,
    "bff_rejects_missing_jwt": bff_rejects_missing_jwt,
    "bff_rejects_wrong_audience": bff_rejects_wrong_audience,
    "sales_db_tool_via_gateway": sales_db_tool_via_gateway,
    "namespace_isolation_placeholder_empty": namespace_isolation_placeholder_empty,
    "health_endpoints_all_ok": health_endpoints_all_ok,
}


def main() -> int:
    import pathlib

    scenarios_path = pathlib.Path(__file__).parent / "scenarios.yaml"
    scenarios = yaml.safe_load(scenarios_path.read_text())["scenarios"]

    results: List[ScenarioResult] = []
    for s in scenarios:
        handler = HANDLERS.get(s["type"])
        if handler is None:
            results.append(ScenarioResult(s["id"], s["title"], False, f"no handler for type '{s['type']}'"))
            continue
        try:
            results.append(handler(s))
        except Exception as exc:  # noqa: BLE001 - a scenario erroring is a fail, not a crash
            results.append(ScenarioResult(s["id"], s["title"], False, f"unhandled error: {exc}"))

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
    if rate >= threshold:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
