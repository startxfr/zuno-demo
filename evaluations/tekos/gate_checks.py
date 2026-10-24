#!/usr/bin/env python3
"""Layered acceptance-gate capability checks required by ADR-0053 that are
neither part of the fixed 20-scenario Tekos acceptance count (ADR-0027 -
scenarios.yaml/run_scenarios.py) nor security-negative checks tied to a
specific identity/classification ADR (security_checks.py). ADR-0053's own
Decision text names "local model inference" and "permitted SaaS fallback"
as checks `make check` must run; local model inference is already proven
live by scenarios 8/9 (a real token stream from the always-preferred local
provider), so one genuine gap this file closes is "permitted SaaS
fallback" - config-consistency only, no live cluster needed, same style
and for the same reason as run_scenarios.py's model_router_fails_closed/
model_router_prefers_local: proving a live SaaS *fallback* would require
deliberately breaking the local model's availability, which a `make check`
gate has no safe way to do and shouldn't attempt.

Two further checks close gaps a stress-testing pass over Tekos surfaced:
`write-code` (ADR-0417, Tekos's newest
declared task) never had a task-specific model-routing check - scenarios
14/15 only assert the generic C1/C3 provider-kind invariant - and nothing
anywhere asserted Tekos's OKF bundle stays free of the DAT-drafting/
image-generation capabilities that belong to Arkos alone
(agents/arkos/tasks/draft-architecture-testimonial.md, ADR-0415).

Like security_checks.py, every check here is mandatory (100%) - these are
capability guarantees ADR-0053 requires (plus the two closed gaps above),
not part of the 75% quality threshold reserved for the fixed 20 scenarios.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

import yaml

# WP-165: agents and the corp policies come from the admitted release.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "common"))
from okf_release import agent_declaration, okf_root, task_declarations  # noqa: E402

try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def c2_permits_saas_fallback_when_not_local_only() -> CheckResult:
    """ADR-0053 "permitted SaaS fallback": unlike C3 (local-only, see
    run_scenarios.py's model_router_fails_closed), C2 must remain able to
    fall back to an approved SaaS provider when nothing source-level
    (ADR-0035's X-Zuno-Local-Only, e.g. Confluence content - see
    security_checks.py's confluence_policy_is_c2_and_local_only and
    ai_gateway_local_only_forces_local_provider) forces local-only. This
    checks platform/ai-gateway/provider-routing.yaml directly, the same
    config components/ai-gateway/app/routing.py's RoutingTable.candidates_for
    loads at runtime.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    routing = yaml.safe_load((repo_root / "platform/ai-gateway/provider-routing.yaml").read_text())
    providers = routing.get("providers", [])
    saas_c2_providers = [p["name"] for p in providers if p.get("kind") == "saas" and "C2" in p.get("eligible_for", [])]
    ok = len(saas_c2_providers) > 0
    return CheckResult(
        "c2_permits_saas_fallback_when_not_local_only",
        ok,
        f"C2-eligible SaaS providers={saas_c2_providers}",
    )


def tekos_write_code_prefers_mistral_codestral() -> CheckResult:
    """ADR-0417: Tekos's `write-code` task must genuinely prefer
    `mistral-codestral` first, and must remain non-strict (unlike Arkos's
    `strict: true` for the same task - Arkos seeds C3 and wants a Codestral
    failure to surface as a visible error, Tekos seeds C1 and deliberately
    wants a silent drop to a local model instead). Checks
    policies/model-routing/model-routing-policy.yaml directly (same style
    as c2_permits_saas_fallback_when_not_local_only above), cross-checked
    against platform/ai-gateway/provider-routing.yaml so the preference
    doesn't name a provider Tekos could never actually reach at its C1
    ceiling. Closes a real gap: scenarios 14/15 only assert the generic
    C1/C3 provider-kind invariant, nothing write-code- or
    Codestral-specific, despite write-code being one of only 4 declared
    Tekos tasks and the newest one.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    policy = yaml.safe_load((okf_root(repo_root) / "policies/model-routing/model-routing-policy.yaml").read_text())
    routing = yaml.safe_load((repo_root / "platform/ai-gateway/provider-routing.yaml").read_text())

    entry = next(
        (p for p in policy.get("preferences", []) if p.get("agent") == "tekos" and p.get("task") == "write-code"),
        None,
    )
    prefer = (entry or {}).get("prefer", [])
    strict = (entry or {}).get("strict", False)

    codestral = next((p for p in routing.get("providers", []) if p["name"] == "mistral-codestral"), None)
    codestral_c1_eligible = bool(codestral) and "C1" in codestral.get("eligible_for", [])

    ok = bool(prefer) and prefer[0] == "mistral-codestral" and codestral_c1_eligible and not strict
    return CheckResult(
        "tekos_write_code_prefers_mistral_codestral",
        ok,
        f"prefer={prefer} strict={strict} codestral_c1_eligible={codestral_c1_eligible}",
    )


def tekos_declares_no_dat_or_image_generation_capability() -> CheckResult:
    """The boundary this whole exercise probes, statically: Tekos's OKF
    bundle must never declare Arkos's `draft-architecture-testimonial` task,
    and none of Tekos's own declared tasks may list `image.generation.create`
    (or its legacy alias `generate_image`) in `allowed_tools` - both names
    entitle a task to the image tool. A pure config-consistency check, no
    live cluster needed - the live/behavioral counterpart (no photorealistic
    image ever appears on a real chat turn) lives in security_checks.py's
    unifai_tekos_never_generates_photorealistic_images.

    ADR-0516: deliberately does NOT check `diagram.generation.create` -
    Tekos's answer-technical-question task legitimately declares that one
    (a carve-out, not a boundary violation; see that task's own frontmatter
    comment). This function's assertion is unchanged by that addition since
    it only ever looked for `image.generation.create`/`generate_image`.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    tasks = agent_declaration(okf_root(repo_root), "tekos").get("tasks", [])
    declarations = task_declarations(okf_root(repo_root), "tekos")
    dat_declared = "draft-architecture-testimonial" in tasks

    image_gen_tasks = []
    for task_name in tasks:
        if task_name not in declarations:
            continue
        allowed_tools = declarations[task_name].get("allowed_tools", [])
        if "image.generation.create" in allowed_tools or "generate_image" in allowed_tools:
            image_gen_tasks.append(task_name)

    ok = not dat_declared and not image_gen_tasks
    return CheckResult(
        "tekos_declares_no_dat_or_image_generation_capability",
        ok,
        f"dat_declared={dat_declared} tasks_with_image_gen={image_gen_tasks}",
    )


def arkos_declares_no_photorealistic_image_generation_capability() -> CheckResult:
    """Policy update (post-ADR-0516): photorealistic image generation is
    now Comage-exclusive, scoped to marketing visuals - Arkos's own former
    `image.generation.create` grant (ADR-0415) was removed from both its
    tasks, since its actual use cases are all diagram-shaped and covered
    by `generate_diagram`. Pure config-consistency check, mirroring
    tekos_declares_no_dat_or_image_generation_capability's own shape - the
    live/behavioral counterpart lives in evaluations/arkos/
    security_checks.py's unifai_arkos_never_generates_photorealistic_images.

    Deliberately does NOT check `diagram.generation.create` - Arkos
    legitimately declares that one on both its tasks.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    tasks = agent_declaration(okf_root(repo_root), "arkos").get("tasks", [])
    declarations = task_declarations(okf_root(repo_root), "arkos")

    image_gen_tasks = []
    for task_name in tasks:
        if task_name not in declarations:
            continue
        allowed_tools = declarations[task_name].get("allowed_tools", [])
        if "image.generation.create" in allowed_tools or "generate_image" in allowed_tools:
            image_gen_tasks.append(task_name)

    ok = not image_gen_tasks
    return CheckResult(
        "arkos_declares_no_photorealistic_image_generation_capability",
        ok,
        f"tasks_with_image_gen={image_gen_tasks}",
    )


def tekos_retriever_finds_red_hat_docs_for_a_basic_openshift_question() -> CheckResult:
    """The Red Hat documentation is ingested and served to Tekos: the UnifAI
    retriever (query.bearer, the path UnifAI's knowledge-tekos retriever uses),
    queried as a Tekos persona over the WEB sources tagged knowledge.tech,
    returns at least one passage from docs.redhat.com for a basic OpenShift
    question. Retrieval only, no model in the loop, so the result does not
    depend on how an answer is worded. Runs in a pod labelled
    zuno.io/rag-client=true (the rag server's NetworkPolicy)."""
    import os

    import httpx
    import run_scenarios

    url = os.getenv("UNIFAI_RAG_URL", "http://unifai-rag-server.zuno-unifai.svc:13456")
    persona = os.getenv("UNIFAI_RAG_PERSONA", "consultant-01")
    resp = httpx.get(
        f"{url}/api/sources/query.bearer",
        params={
            "query": "What is a namespace in OpenShift?",
            "sourceType": "WEB",
            "tags": "knowledge.tech",
            "top_k_results": 5,
        },
        headers={"Authorization": f"Bearer {run_scenarios.get_token(persona)}"},
        timeout=30,
    )
    if resp.status_code != 200:
        return CheckResult(
            "tekos_retriever_finds_red_hat_docs_for_a_basic_openshift_question", False,
            f"query.bearer status={resp.status_code}",
        )
    matches = resp.json().get("matches", [])
    # The source URL's metadata key is not part of a stable contract; any
    # metadata value naming docs.redhat.com counts.
    from_docs = [
        m for m in matches
        if any("docs.redhat.com" in str(v) for v in (m.get("metadata") or {}).values())
    ]
    return CheckResult(
        "tekos_retriever_finds_red_hat_docs_for_a_basic_openshift_question",
        bool(from_docs),
        f"matches={len(matches)} from_docs_redhat_com={len(from_docs)}",
    )


CHECKS = [
    c2_permits_saas_fallback_when_not_local_only,
    tekos_write_code_prefers_mistral_codestral,
    tekos_declares_no_dat_or_image_generation_capability,
    arkos_declares_no_photorealistic_image_generation_capability,
    tekos_retriever_finds_red_hat_docs_for_a_basic_openshift_question,
]


def run() -> list[CheckResult]:
    results = []
    for check in CHECKS:
        try:
            result = check()
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            result = CheckResult(check.__name__, False, f"unhandled error: {exc}")
        results.append(result)
        log_test_line("tekos", "gate", result.name, result.name, result.passed, result.detail)
    return results


def main() -> int:
    results = run()
    print(f"{'PASS':<6}{'CHECK'}")
    for r in results:
        print(f"{'✓' if r.passed else '✗':<6}{r.name}")
        if not r.passed and r.detail:
            print(f"      -> {r.detail}")

    if all(r.passed for r in results):
        print("\nRESULT: PASS")
        return 0
    print("\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
