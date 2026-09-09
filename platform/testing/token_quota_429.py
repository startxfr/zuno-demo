#!/usr/bin/env python3
"""ADR-0555/WP-142: the live TOKEN-budget-exceedance proof, generalized
across every stresstest-covered agent (tekos/arkos/comage) - the token
counterpart to `quota_429.py`'s request-RATE proof.

What it drives: AI Gateway's own token-budget ledger
(components/ai-gateway/app/quota.py, `quota.ledger.check()` ->
`app/main.py`'s `return JSONResponse(denial.detail(), status_code=429)`),
selected via the `X-Zuno-Quota-Class: stresstest` request header against
the dedicated `stresstest` class in policies/quotas/quota-policy.yaml
(deliberately tiny - 2000 tokens/5m per user - so a handful of short real
chat calls exhaust it, keeping the real-inference/GPU cost of proving
enforcement marginal on a GPU-quota-constrained cluster). Calls
AI Gateway's `/v1/chat/completions` directly (same in-cluster pattern
`evaluations/*/security_checks.py`'s own
`ai_gateway_local_only_forces_local_provider` check already uses), not
through the full agent-runtime/BFF stack - `zuno.quota_class` has no
frontmatter-driven path from a real task to this header today, so this is
the same class of deliberate, direct, boundary-scoped probe those checks
already are.

NOT RHOAI MaaS's own Kuadrant/Limitador TokenRateLimitPolicy (the `/sales`
MaaSSubscription tier, gitops/charts/models/values.yaml) - live-verified
2026-09-09 that path is currently UNREACHABLE by any persona-driven
request: `maas-gateway-auth`'s AuthPolicy
(openshift-ingress/maas-gateway-auth) only accepts `Bearer sk-oai-*` API
keys or Kubernetes ServiceAccount TokenReview, no Keycloak-JWT
authentication method at all (`oc get authpolicy maas-gateway-auth -n
openshift-ingress -o yaml` - confirmed no `openshift-jwt`/oidc rule),
because `ModelsAsService.spec.externalOIDC` (the flag
components/ai-gateway/app/maas_adapter.py's own `_maas_bearer_token`
comment names as the prerequisite) is not yet set on this cluster. A
`sale-01` (the `/sales`-group demo persona) Keycloak token sent straight
at MaaS's own `/zuno-ai-run/gpt-oss-20b/v1/chat/completions` route
returns 401, confirmed live before writing this file. Enabling
externalOIDC is a separate, cluster-wide MaaS-authentication decision with
its own security review, not a side effect of a stresstest scenario - left
as a known, documented gap (ADR-0555's "Known out-of-scope gaps") rather
than silently claimed as covered.

Prints a JSON array of Day2Result rows to stdout, same convention as
day2_stresstest.py, day2_bulk.py and quota_429.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from day2_report import Day2Result, log_test_line  # noqa: E402

AGENT = os.getenv("AGENT", "tekos")
PERSONA = os.getenv("STRESS_TEST_PERSONA", "consultant-01")
TOKEN_QUOTA_TIMEOUT_SECONDS = float(os.getenv("TOKEN_QUOTA_TIMEOUT_SECONDS", "30"))
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")

# Mirrors policies/quotas/quota-policy.yaml's `stresstest` class - asserted
# against, not read from, that file on purpose (same reasoning as
# quota_429.py's STANDARD/INTENSIVE_USER_LIMIT): a generator bug that
# dropped the budget would still pass a check deriving its own expectation
# from the same source it is validating.
STRESSTEST_USER_TOKEN_BUDGET = int(os.getenv("TOKEN_QUOTA_STRESSTEST_BUDGET", "2000"))
# Each call's max_tokens - bounds both the per-call cost and how many calls
# are needed to exhaust the budget above (2000 // 150 + headroom ~= 16-20).
CALL_MAX_TOKENS = int(os.getenv("TOKEN_QUOTA_CALL_MAX_TOKENS", "120"))
BURST_HEADROOM_CALLS = int(os.getenv("TOKEN_QUOTA_BURST_HEADROOM_CALLS", "8"))
MAX_CALLS = (STRESSTEST_USER_TOKEN_BUDGET // max(CALL_MAX_TOKENS, 1)) + BURST_HEADROOM_CALLS


def _auth_headers() -> Dict[str, str]:
    # Same escape hatch as quota_429.py: TOKEN_QUOTA_TOKEN overrides with an
    # already-minted access token for standalone/off-cluster runs.
    token = os.getenv("TOKEN_QUOTA_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}

    import run_scenarios

    return run_scenarios.auth_headers(PERSONA)


def _burst(headers: Dict[str, str]) -> Tuple[Optional[int], List[int], Optional[str]]:
    """Send short real chat completions, tagged X-Zuno-Quota-Class:
    stresstest, until a 429 or MAX_CALLS is reached. Sequential, not
    concurrent - same reasoning as quota_429.py's _burst: the ledger's
    counter is shared, concurrency only blurs which call crossed it.
    """
    statuses: List[int] = []
    first_429: Optional[int] = None
    first_429_body: Optional[str] = None
    call_headers = dict(headers, **{"X-Zuno-Quota-Class": "stresstest"})
    with httpx.Client(timeout=TOKEN_QUOTA_TIMEOUT_SECONDS) as client:
        for i in range(MAX_CALLS):
            try:
                resp = client.post(
                    f"{AI_GATEWAY_URL}/v1/chat/completions",
                    headers=call_headers,
                    json={
                        "model": "zuno-auto",
                        "messages": [{
                            "role": "user",
                            "content": (
                                "Write a short paragraph (at least 80 words) "
                                "about Kubernetes namespaces."
                            ),
                        }],
                        "max_tokens": CALL_MAX_TOKENS,
                    },
                )
                status = resp.status_code
            except Exception as exc:  # noqa: BLE001 - a transport error is a datapoint, not a crash
                log_test_line(AGENT, "token_quota", f"call-{i}", f"call {i + 1}/{MAX_CALLS}", False, f"error: {exc}")
                statuses.append(0)
                continue
            statuses.append(status)
            if status == 429 and first_429 is None:
                first_429 = i
                first_429_body = (resp.text or "")[:200]
            log_test_line(
                AGENT, "token_quota", f"call-{i}", f"call {i + 1}/{MAX_CALLS}",
                status < 500, f"status={status}",
            )
            if first_429 is not None:
                break
    return first_429, statuses, first_429_body


def run() -> List[Day2Result]:
    # advantage/finage/naveo are still placeholders with no real chat
    # backend - same coverage no-op as quota_429.py's own gate.
    if AGENT not in ("tekos", "arkos", "comage"):
        return [Day2Result(
            AGENT, "token_quota", "n/a", "coverage", True,
            "the stresstest token-budget proof only covers stresstest-"
            f"active agents (tekos/arkos/comage) today - {AGENT} is still "
            "a placeholder",
        )]

    headers = _auth_headers()
    first_429, statuses, body = _burst(headers)
    results: List[Day2Result] = []

    sent = len(statuses)
    if first_429 is None:
        results.append(Day2Result(
            AGENT, "token_quota", "stresstest-429", "quota", False,
            f"no 429 in {sent} calls (budget={STRESSTEST_USER_TOKEN_BUDGET} "
            f"tokens/5m, max_tokens/call={CALL_MAX_TOKENS}, "
            f"statuses={sorted(set(statuses))}) status=0",
        ))
    else:
        results.append(Day2Result(
            AGENT, "token_quota", "stresstest-429", "quota", True,
            f"first 429 at call {first_429 + 1}/{sent} "
            f"(budget={STRESSTEST_USER_TOKEN_BUDGET} tokens/5m, "
            f"max_tokens/call={CALL_MAX_TOKENS}) status=429",
        ))

    server_errors = [s for s in statuses if s >= 500]
    results.append(Day2Result(
        AGENT, "token_quota", "no-server-error", "quota", not server_errors,
        f"{len(server_errors)} 5xx across {len(statuses)} calls"
        + (f" (first status={server_errors[0]})" if server_errors else ""),
    ))

    if body is not None:
        log_test_line(AGENT, "token_quota", "429-body", "quota error body", True, body.replace("\n", " ")[:120])

    return results


def main() -> int:
    results = run()
    print(json.dumps([asdict(r) for r in results]))
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
