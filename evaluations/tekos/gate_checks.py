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

Two further checks close gaps a stress-testing pass over Tekos surfaced
(see stress_test.py's module docstring for the live/behavioral counterparts
of these same two guarantees): `write-code` (ADR-0417, Tekos's newest
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
    policy = yaml.safe_load((repo_root / "policies/model-routing/model-routing-policy.yaml").read_text())
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
    (or its legacy alias `generate_image`) in `allowed_tools` - mirroring
    components/agent-runtime/app/graph/nodes.py's own alias-tolerant check
    for whether a task is entitled to the generate_image tool. A pure
    config-consistency check, no live cluster needed - the live/behavioral
    counterpart (no photorealistic image ever appears on a real chat turn)
    lives in security_checks.py's
    tekos_chat_never_returns_photorealistic_images.

    ADR-0516: deliberately does NOT check `diagram.generation.create` -
    Tekos's answer-technical-question task legitimately declares that one
    (a carve-out, not a boundary violation; see that task's own frontmatter
    comment). This function's assertion is unchanged by that addition since
    it only ever looked for `image.generation.create`/`generate_image`.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    bundle = yaml.safe_load(
        (repo_root / "agents/tekos/agent.okf.md").read_text().split("---", 2)[1]
    )
    tasks = bundle.get("zuno", {}).get("tasks", [])
    dat_declared = "draft-architecture-testimonial" in tasks

    image_gen_tasks = []
    for task_name in tasks:
        task_path = repo_root / "agents/tekos/tasks" / f"{task_name}.md"
        if not task_path.exists():
            continue
        task_frontmatter = yaml.safe_load(task_path.read_text().split("---", 2)[1])
        allowed_tools = task_frontmatter.get("zuno", {}).get("allowed_tools", [])
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
    security_checks.py's arkos_chat_never_returns_photorealistic_images.

    Deliberately does NOT check `diagram.generation.create` - Arkos
    legitimately declares that one on both its tasks.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    bundle = yaml.safe_load(
        (repo_root / "agents/arkos/agent.okf.md").read_text().split("---", 2)[1]
    )
    tasks = bundle.get("zuno", {}).get("tasks", [])

    image_gen_tasks = []
    for task_name in tasks:
        task_path = repo_root / "agents/arkos/tasks" / f"{task_name}.md"
        if not task_path.exists():
            continue
        task_frontmatter = yaml.safe_load(task_path.read_text().split("---", 2)[1])
        allowed_tools = task_frontmatter.get("zuno", {}).get("allowed_tools", [])
        if "image.generation.create" in allowed_tools or "generate_image" in allowed_tools:
            image_gen_tasks.append(task_name)

    ok = not image_gen_tasks
    return CheckResult(
        "arkos_declares_no_photorealistic_image_generation_capability",
        ok,
        f"tasks_with_image_gen={image_gen_tasks}",
    )


CHECKS = [
    c2_permits_saas_fallback_when_not_local_only,
    tekos_write_code_prefers_mistral_codestral,
    tekos_declares_no_dat_or_image_generation_capability,
    arkos_declares_no_photorealistic_image_generation_capability,
]


def run() -> list[CheckResult]:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            results.append(CheckResult(check.__name__, False, f"unhandled error: {exc}"))
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
