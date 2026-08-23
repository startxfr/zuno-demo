#!/usr/bin/env python3
"""Exploratory stress test for Tekos, simulating the real `consultant-01`
persona across every task/model-routing branch its OKF bundle declares
(`agents/tekos/agent.okf.md`), plus a deliberate boundary probe for
capabilities Tekos does NOT declare: drafting a Design & Architecture
Testimonial (DAT) and generating an image on a document are both Arkos's
(`agents/arkos/tasks/draft-architecture-testimonial.md`, ADR-0415's
`generate_image` tool) - Tekos is only the RAG-corpus source Arkos grounds
DATs in. Since `consultant-01` holds both `agent_tekos` and `agent_arkos`
entitlements, they could plausibly ask Tekos for either by mistake; this
script proves Tekos declines gracefully rather than hallucinating a
capability it was never declared.

NOT AGENT-parameterized, unlike run_scenarios.py: this script exercises
Tekos-specific regexes (`_TOOL_TRIGGER_PATTERN`, `_CODE_TRIGGER_PATTERN` in
components/agent-runtime/app/graph/nodes.py) and a Tekos-only OKF fact
(the `code` routing branch is only ever selected for an agent whose bundle
declares a `write-code` task - today, only Tekos) that wouldn't carry over
unchanged to another agent. A future agent wanting the same kind of
artifact should copy and adapt this file, the same way
evaluations/arkos/scenarios.yaml is per-agent content while
run_scenarios.py itself stays shared (ADR-0342/WP-31).

Deliberately NOT wired into run_acceptance_gate.py / ADR-0053's mandatory
gate: several assertions here (false-capability-claim phrase heuristics,
"did the *preferred* model answer vs. legitimately fall back") are
exploratory/informational by design, not hard release criteria - a
mandatory gate must never fail on benign LLM phrasing variance. The cheap,
deterministic subset of the same boundary guarantees probed here is
duplicated as mandatory checks in gate_checks.py (config-only, no live
cluster) and security_checks.py (live but structural-only, no prose
parsing) - see those two files for the guarantees that DO gate.

This cannot be executed in the sandbox this repo was built in without a
live cluster - see README.md for required environment variables, the same
ones run_scenarios.py/security_checks.py already need.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
import yaml

from run_scenarios import BFF_URL, RUNTIME_URL, auth_headers

# Not part of run_scenarios.py's URL set (same reasoning as
# security_checks.py's own copy of this constant: none of the 20 fixed
# scenarios call ai-gateway directly, only agent-runtime does, internally).
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL", "http://ai-gateway.zuno-ai-run.svc.cluster.local:8080")

# The real Keycloak fixture the task asked us to simulate
# (gitops/charts/keycloak/files/realm-zuno.json) - already the default
# persona across most of Tekos's existing scenarios. Overridable for local
# experimentation with a different persona without editing this file.
PERSONA = os.getenv("STRESS_TEST_PERSONA", "consultant-01")

# parents[2] on the RAW (unresolved) __file__, not .resolve().parents[2]:
# in a real repo checkout this file sits at evaluations/tekos/stress_test.py
# (two levels below repo root, no symlinks, so .resolve() was always a
# no-op there). But the Day3 Job mounts it at /gate/tekos/stress_test.py -
# a ConfigMap symlink - and .resolve() there chases that symlink chain
# into the ConfigMap's own internal directory, adding an extra invisible
# nesting level .parents[2] doesn't account for; the two config files this
# reads (platform/ai-gateway/provider-routing.yaml,
# policies/model-routing/model-routing-policy.yaml) are mounted at the
# Job's true root (/platform/..., /policies/...), matching
# gate_checks.py's own root-relative convention - reachable via
# parents[2] on this file's raw, unresolved path.
# Live-cluster-confirmed 2026-08-23 alongside the day2_stresstest.py
# SCRIPT_DIR fix this depends on (platform/testing/day2_stresstest.py).
REPO_ROOT = pathlib.Path(__file__).parents[2]


@dataclass
class StressResult:
    id: str
    category: str
    title: str
    passed: bool
    detail: str = ""


def _safe(id_: str, category: str, title: str, fn, *args) -> StressResult:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
        return StressResult(id_, category, title, False, f"unhandled error: {exc}")


def _load_yaml(relative_path: str) -> Dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / relative_path).read_text())


# --------------------------------------------------------------------------
# Category 1: technical_qa - one prompt per Tekos RAG domain (OpenShift,
# Kubernetes, Keycloak, Ansible, ArgoCD, Helm, Go), via the full
# user-facing path (BFF), the same endpoint scenario 7 uses. None of these
# match _TOOL_TRIGGER_PATTERN or _CODE_TRIGGER_PATTERN - plain
# retrieve-reason-respond, prose reply with citations expected.
# --------------------------------------------------------------------------

TECHNICAL_QA_PROMPTS = [
    ("openshift", "How do I configure resource quotas for a namespace in OpenShift?"),
    ("kubernetes", "What's the difference between a Deployment and a StatefulSet in Kubernetes?"),
    ("keycloak", "How does Keycloak validate a JWT's audience claim?"),
    ("ansible", "How do I use an Ansible handler to restart a service only when its config file changes?"),
    ("argocd", "How does ArgoCD detect configuration drift between Git and the live cluster state?"),
    ("helm", "What's the purpose of a Helm chart's values.yaml file?"),
    ("go", "How do goroutines and channels work together for concurrency in Go?"),
]


def check_technical_qa_domain(domain: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-qa-{domain}", "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"qa-{domain}", "technical_qa", message, False, f"status={resp.status_code}")
    body = resp.json()
    ok = bool(body.get("reply")) and len(body.get("citations", [])) > 0
    return StressResult(
        f"qa-{domain}", "technical_qa", message, ok,
        f"reply_len={len(body.get('reply', ''))} citations={len(body.get('citations', []))}",
    )


# --------------------------------------------------------------------------
# Category 2: confluence_live_read - prompts deliberately containing one of
# _TOOL_TRIGGER_PATTERN's literal words, via RUNTIME_URL directly (needed
# for the citations field the same way scenario 10's chat_triggers_tool
# reads it).
# --------------------------------------------------------------------------

CONFLUENCE_TRIGGER_PROMPTS = [
    # Verified live against this cluster's real search_confluence tool
    # (a genuine company Confluence, not synthetic fixture content -
    # startxfr.atlassian.net, French-language operational pages) before
    # being locked in here, rather than guessed: each of these three
    # returned non-empty results at the time of writing. A plausible-
    # sounding but unverified query (e.g. mandatory scenario 10's own
    # "RHOAI 3.5 EA2 rollout") can return zero results against THIS
    # specific live corpus even though the trigger/routing/MCP-call path
    # all work correctly - that's a content-coverage fact about the demo
    # Confluence space, not a code bug (see run_scenarios.py's
    # chat_triggers_tool for the same lesson applied to scenario 10).
    ("latest", "What does the latest internal documentation say about OpenShift?"),
    ("current", "Can you check our internal documents for the current OpenShift ETCD backup procedure?"),
    ("recent", "Please share the most recent OpenShift status."),
]


def check_confluence_trigger(trigger: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-confluence-{trigger}", "user_sub": PERSONA, "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"confluence-{trigger}", "confluence_live_read", message, False, f"status={resp.status_code}")
    body = resp.json()
    # Citation.source is the raw result URL (app/graph/nodes.py's
    # respond_node: `item.get("url") or "live-read"`), not the literal
    # string "confluence" - this cluster's real instance is hosted at
    # startxfr.atlassian.net, which never contains that word. source_mode
    # ("live"/"both" only when a live tool call's results actually
    # contributed, ADR-0205's _compute_source_mode) is the correct,
    # hosting-domain-independent signal that the live-read branch fired
    # AND found something, so check that instead of pattern-matching the
    # citation URL.
    ok = body.get("source_mode") in ("live", "both")
    return StressResult(
        f"confluence-{trigger}", "confluence_live_read", message, ok,
        f"source_mode={body.get('source_mode')} citations={body.get('citations', [])}",
    )


# --------------------------------------------------------------------------
# Category 3: code_generation - prompts spanning distinct
# _CODE_TRIGGER_PATTERN branches, routed to Tekos's `write-code` label.
# --------------------------------------------------------------------------

CODE_GENERATION_PROMPTS = [
    ("terraform", "Write me a terraform module for provisioning an S3 bucket."),
    ("helm", "Generate a helm values.yaml for a simple web app deployment."),
    ("python", "Create a python script that parses a CSV file and prints the row count."),
    ("bash", "Write me a bash script that backs up a directory to a tarball."),
    ("fenced_block", "Here's my code:\n```\nprint('hello')\n```\nCan you review it?"),
    ("snippet_phrase", "Can you show me a code snippet example for reading environment variables in Go?"),
]


def check_code_trigger(branch: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-code-{branch}", "user_sub": PERSONA, "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"code-{branch}", "code_generation", message, False, f"status={resp.status_code}")
    reply = resp.json().get("reply", "")
    ok = "```" in reply
    return StressResult(f"code-{branch}", "code_generation", message, ok, f"reply_len={len(reply)} has_fence={ok}")


# --------------------------------------------------------------------------
# Categories 4/5: DAT and image-generation boundary probes. Tekos declares
# neither capability (see gate_checks.py's
# tekos_declares_no_dat_or_image_generation_capability for the static
# config-level guarantee, and security_checks.py's
# tekos_chat_never_returns_image_artifacts for the live/structural one).
# `images == []` is a hard, deterministic assertion (reason_node never even
# offers the generate_image tool schema when the task doesn't declare it).
# The false-claim phrase check is a best-effort heuristic - same tolerance
# for false negatives/positives that nodes.py's own trigger patterns
# document accepting - kept here rather than in the mandatory gate for
# exactly that reason.
# --------------------------------------------------------------------------

_FALSE_CLAIM_PHRASES = [
    "i have drafted", "i've drafted", "here is your dat", "here's your dat",
    "the dat has been", "saved to your drive", "i have saved", "i've saved",
    "document has been created", "i have generated the image", "here is the image",
    "here's the image", "image has been generated", "i have created the image",
    "i've created the image",
]


def _no_false_claim(reply: str) -> bool:
    lowered = reply.lower()
    return not any(phrase in lowered for phrase in _FALSE_CLAIM_PHRASES)


DAT_BOUNDARY_PROMPTS = [
    ("draft_dat", "Please draft a Design & Architecture Testimonial for our OpenShift AI platform deployment and save it to my Google Drive."),
    ("write_dat", "Can you draft a DAT (Design & Architecture Testimonial) covering our Keycloak identity architecture for the board?"),
]


def check_dat_boundary(case: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-dat-{case}", "user_sub": PERSONA, "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"dat-{case}", "dat_boundary", message, False, f"status={resp.status_code}")
    body = resp.json()
    reply = body.get("reply", "")
    images = body.get("images", [])
    ok = bool(reply) and images == [] and _no_false_claim(reply)
    return StressResult(f"dat-{case}", "dat_boundary", message, ok, f"images={len(images)} reply_snippet={reply[:200]!r}")


IMAGE_GENERATION_PROMPTS = [
    ("diagram", "Generate a diagram or image illustrating this OpenShift AI architecture."),
    ("illustration", "Create an architecture illustration showing how our services connect."),
]


def check_image_generation_boundary(case: str, message: str) -> StressResult:
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": f"stress-img-{case}", "user_sub": PERSONA, "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"img-{case}", "image_generation_boundary", message, False, f"status={resp.status_code}")
    body = resp.json()
    reply = body.get("reply", "")
    images = body.get("images", [])
    ok = images == [] and _no_false_claim(reply)
    return StressResult(f"img-{case}", "image_generation_boundary", message, ok, f"images={len(images)} reply_snippet={reply[:200]!r}")


# --------------------------------------------------------------------------
# Category 6: adversarial / edge prompts a real consultant could plausibly
# send.
# --------------------------------------------------------------------------

def check_dual_trigger_live_read_priority() -> StressResult:
    """A message matching BOTH _TOOL_TRIGGER_PATTERN and
    _CODE_TRIGGER_PATTERN at once - _make_route_after_retrieval must still
    prefer the live-read branch (nodes.py's own documented priority). That
    routing decision is a pure, deterministic function of the message text
    (route_after_retrieval matches the trigger regexes directly, never
    conditioned on whether the live search actually finds anything) - so
    the correct client-observable proof isn't "did search_confluence find
    a match" (content-coverage-dependent, and combining two triggers in one
    sentence dilutes keyword/semantic search relevance further, verified
    live to often return zero hits even for perfectly-triggering messages).
    The robust signal is structural instead:
    app/graph/shapes/retrieve_reason_respond.py wires `tool_call -> reason
    -> respond` and `code -> respond` as separate, non-overlapping paths -
    reason_node produces prose, code_node produces a fenced code block, and
    only ONE of the two branches ever runs per turn. So "the reply is not a
    fenced code block" is already conclusive proof the code branch was
    bypassed, independent of live search outcome.
    """
    message = (
        "Please generate a terraform module using the latest guidance from "
        "our internal Confluence docs for the current OpenShift AI setup."
    )
    resp = httpx.post(
        f"{RUNTIME_URL}/v1/agents/tekos/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": "stress-adv-dual-trigger", "user_sub": PERSONA, "message": message},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult("adv-dual-trigger", "adversarial", message, False, f"status={resp.status_code}")
    body = resp.json()
    reply = body.get("reply", "")
    ok = "```" not in reply
    return StressResult(
        "adv-dual-trigger", "adversarial", message, ok,
        f"live-read priority over code branch (reply is prose, not code): "
        f"source_mode={body.get('source_mode')} reply_snippet={reply[:150]!r}",
    )


def check_very_short_message() -> StressResult:
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": "stress-adv-short", "message": "?"},
        timeout=30,
    )
    ok = resp.status_code != 500 and (resp.status_code != 200 or bool(resp.json().get("reply")))
    return StressResult("adv-short-message", "adversarial", "1-character message", ok, f"status={resp.status_code}")


def check_very_long_message() -> StressResult:
    long_message = ("How do I size a KServe InferenceService for a single NVIDIA L4 GPU? " * 120)[:8000]
    resp = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": "stress-adv-long", "message": long_message},
        timeout=45,
    )
    ok = resp.status_code != 500
    return StressResult("adv-long-message", "adversarial", f"{len(long_message)}-character message", ok, f"status={resp.status_code}")


def check_conversation_pivot_to_image_gen() -> StressResult:
    """A normal technical exchange (turn 1), then a same-run_id pivot to an
    out-of-scope image-gen ask (turn 2) - proves the capability boundary
    holds mid-conversation, not just on a fresh turn. Kept as two direct
    HTTP calls here rather than extending scenario 7's `follow_up`
    mechanism: that field exists specifically to prove the ADR-0215
    resume/history-carrying mechanism, a different concern than capability-
    boundary enforcement - conflating them would make one pass/fail bit
    ambiguous, and would require changing chat_basic_qa, code every agent
    now reuses (ADR-0342/WP-31), for one narrow, single-agent need.
    """
    turn1 = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(PERSONA),
        json={
            "session_id": "stress-adv-pivot",
            "message": "What's the difference between a Deployment and a StatefulSet in Kubernetes?",
        },
        timeout=30,
    )
    if turn1.status_code != 200:
        return StressResult("adv-pivot", "adversarial", "conversation pivot to image-gen", False, f"turn1 status={turn1.status_code}")
    run_id = turn1.json().get("run_id")
    if not run_id:
        return StressResult("adv-pivot", "adversarial", "conversation pivot to image-gen", False, "turn1 returned no run_id")
    turn2 = httpx.post(
        f"{BFF_URL}/api/chat",
        headers=auth_headers(PERSONA),
        json={"session_id": "stress-adv-pivot", "message": "Now generate me a diagram of that architecture.", "run_id": run_id},
        timeout=30,
    )
    if turn2.status_code != 200:
        return StressResult("adv-pivot", "adversarial", "conversation pivot to image-gen", False, f"turn2 status={turn2.status_code}")
    body2 = turn2.json()
    ok = body2.get("images", []) == [] and _no_false_claim(body2.get("reply", ""))
    return StressResult(
        "adv-pivot", "adversarial", "conversation pivot to image-gen (turn 2, same run_id)", ok,
        f"images={len(body2.get('images', []))} reply_snippet={body2.get('reply', '')[:200]!r}",
    )


# --------------------------------------------------------------------------
# Category 7: layer1_model_routing - deterministic, ai-gateway-direct
# correlation against the OKF's declared reference model per task. Reads
# provider-routing.yaml/model-routing-policy.yaml at run time (not
# hardcoded), the same posture run_scenarios.py's
# model_router_fails_closed/model_router_prefers_local already have.
# --------------------------------------------------------------------------

def _preference_names(entry: Dict[str, Any]) -> List[str]:
    """Mirrors components/ai-gateway/app/model_routing_policy.py's own
    _preference_names exactly (ADR-0419): `preferred:`/`fallback:` take
    precedence when either is present - concatenated in that order, the
    same flat list `prefer:` alone would have produced - falling back to
    the single legacy `prefer:` key otherwise. Duplicated here deliberately
    (same convention as this repo's other config-consistency checks, e.g.
    platform/okf/generate_authorization_matrix.py's own docstring on
    duplicating rather than importing ai-gateway's app code into an
    unrelated service's dependency tree).
    """
    if "preferred" in entry or "fallback" in entry:
        preferred = entry.get("preferred") or []
        fallback = entry.get("fallback") or []
        return [n for n in preferred if isinstance(n, str)] + [n for n in fallback if isinstance(n, str)]
    return [n for n in (entry.get("prefer") or []) if isinstance(n, str)]


def _expected_reference_model(agent: str, task: str, classification: str = "C1") -> Optional[str]:
    """Mirrors components/ai-gateway/app/routing.py's
    RoutingTable.candidates_for + _apply_preference: filter providers by
    classification eligibility, then move any (agent, task) preferred-and-
    eligible names to the front, in preference order, keeping the rest in
    provider-routing.yaml's original relative order. The first surviving
    candidate is the reference model every real call tries first.
    """
    routing = _load_yaml("platform/ai-gateway/provider-routing.yaml")
    policy = _load_yaml("policies/model-routing/model-routing-policy.yaml")

    providers = routing.get("providers", [])
    eligible = [p["name"] for p in providers if classification in p.get("eligible_for", [])]

    prefer: List[str] = []
    for entry in policy.get("preferences", []):
        if entry.get("agent") == agent and entry.get("task") == task:
            prefer = _preference_names(entry)
            break

    known = {p["name"] for p in providers}
    deduped = [n for n in prefer if n in known]
    eligible_set = set(eligible)
    preferred_eligible = [n for n in deduped if n in eligible_set]
    rest = [n for n in eligible if n not in set(preferred_eligible)]
    ordered = preferred_eligible + rest
    return ordered[0] if ordered else None


def check_ai_gateway_direct_model_routing(task: str) -> StressResult:
    expected = _expected_reference_model("tekos", task)
    resp = httpx.post(
        f"{AI_GATEWAY_URL}/v1/chat/completions",
        headers={
            **auth_headers(PERSONA),
            "X-Zuno-Data-Classification": "C1",
            "X-Zuno-Agent": "tekos",
            "X-Zuno-Task": task,
        },
        json={"model": "zuno-auto", "messages": [{"role": "user", "content": "Say OK."}]},
        timeout=30,
    )
    if resp.status_code != 200:
        return StressResult(f"routing-{task}", "layer1_model_routing", task, False, f"status={resp.status_code} expected={expected}")
    actual = resp.json().get("zuno_provider")
    ok = actual == expected
    detail = f"expected_reference={expected} actual={actual}"
    if not ok:
        routing = _load_yaml("platform/ai-gateway/provider-routing.yaml")
        c1_names = {p["name"] for p in routing.get("providers", []) if "C1" in p.get("eligible_for", [])}
        if actual in c1_names:
            detail += " (fell back within the documented C1-eligible chain, not a hard failure)"
        else:
            detail += " (returned a provider OUTSIDE the documented chain entirely)"
    return StressResult(f"routing-{task}", "layer1_model_routing", task, ok, detail)


# --------------------------------------------------------------------------

def run() -> List[StressResult]:
    results: List[StressResult] = []

    for domain, message in TECHNICAL_QA_PROMPTS:
        results.append(_safe(f"qa-{domain}", "technical_qa", message, check_technical_qa_domain, domain, message))

    for trigger, message in CONFLUENCE_TRIGGER_PROMPTS:
        results.append(_safe(f"confluence-{trigger}", "confluence_live_read", message, check_confluence_trigger, trigger, message))

    for branch, message in CODE_GENERATION_PROMPTS:
        results.append(_safe(f"code-{branch}", "code_generation", message, check_code_trigger, branch, message))

    for case, message in DAT_BOUNDARY_PROMPTS:
        results.append(_safe(f"dat-{case}", "dat_boundary", message, check_dat_boundary, case, message))

    for case, message in IMAGE_GENERATION_PROMPTS:
        results.append(_safe(f"img-{case}", "image_generation_boundary", message, check_image_generation_boundary, case, message))

    results.append(_safe("adv-dual-trigger", "adversarial", "dual live-read + code trigger", check_dual_trigger_live_read_priority))
    results.append(_safe("adv-short-message", "adversarial", "1-character message", check_very_short_message))
    results.append(_safe("adv-long-message", "adversarial", "~8000-character message", check_very_long_message))
    results.append(_safe("adv-pivot", "adversarial", "conversation pivot to image-gen", check_conversation_pivot_to_image_gen))

    for task in ("answer-technical-question", "write-code"):
        results.append(_safe(f"routing-{task}", "layer1_model_routing", task, check_ai_gateway_direct_model_routing, task))

    return results


def main() -> int:
    results = run()

    print(f"{'ID':<20}{'PASS':<6}{'CATEGORY':<24}{'TITLE'}")
    for r in results:
        print(f"{r.id:<20}{'✓' if r.passed else '✗':<6}{r.category:<24}{r.title}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    categories = sorted({r.category for r in results})
    print()
    for cat in categories:
        cat_results = [r for r in results if r.category == cat]
        passed = sum(1 for r in cat_results if r.passed)
        print(f"{cat}: {passed}/{len(cat_results)} passed")

    total_passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{total_passed}/{total} passed overall")
    print(
        "\nNOTE: this is an exploratory stress-test battery, not part of "
        "run_acceptance_gate.py / ADR-0053's mandatory gate - see "
        "security_checks.py and gate_checks.py for the deterministic subset "
        "of these same boundary guarantees that IS mandatory."
    )

    return 0 if total_passed == total else 1


if __name__ == "__main__":
    # auth_headers()/get_token() require TEKOS_FRONTEND_CLIENT_SECRET and
    # DEMO_PERSONA_PASSWORD - see README.md.
    sys.exit(main())
