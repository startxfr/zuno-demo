"""OKF narrowing rule, re-checked at admission (ADR-0579 clause 5, ADR-0615 clause 6, WP-163).

A copy of zuno-demo-agents platform/okf/check_narrowing.py, re-rooted on an
extracted release directory: the rule runs once in the agents repository's
CI and once here, so a misconfigured CI on one side cannot admit a widening
alone. Duplicated on purpose (small, well-specified logic, independent
life cycles - the same convention zuno-demo-agents' validate_okf_bundle.py states); keep the
two in step when the rule changes.

The rules apply from legacy v0.3 up, profile 1.0 included. The gate compares
levels (legacy v0.2 < legacy v0.3 <= profile 1.0), never a version string, so
a new profile can never skip them in silence (ADR-0615 F11). Legacy v0.2
bundles have none of these fields and pass trivially; a bundle whose agent
document declares no supported version is a finding, never a pass.

Used by admit_okf_bundle.py validate.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Set

import yaml

CLASS_ORDER = ["C1", "C2", "C3"]

# ADR-0615 clause 5: which version a document follows. This module keeps its own
# copy of the dispatch rule (ADR-0508 clause 4); platform/okf/tests/
# test_okf_version_dispatch.py checks that every copy accepts and refuses the same
# documents.
UPSTREAM_OKF_VERSION = "0.2"
ZUNO_PROFILES = ("1.0",)
LEGACY_OKF_VERSIONS = ("v0.2", "v0.3")
# ADR-0615 clause 6: narrowing applies at "v0.3 or above". Compare levels, never versions.
LEVEL = {"v0.2": 2, "v0.3": 3, "1.0": 4}


def okf_document_version(front: dict) -> str:
    """The version a document's frontmatter follows: "v0.2" or "v0.3" (legacy)
    or "1.0" (profile). ValueError, naming the cause, for any other pair."""
    version = front.get("okf_version")
    zuno = front.get("zuno")
    profile = zuno.get("profile") if isinstance(zuno, dict) else None
    supported = (f'okf_version "{UPSTREAM_OKF_VERSION}" with zuno.profile {", ".join(ZUNO_PROFILES)}, '
                 f'or legacy {", ".join(LEGACY_OKF_VERSIONS)}')
    if version is None:
        raise ValueError(f"missing okf_version (supported: {supported})")
    if isinstance(version, str) and version in LEGACY_OKF_VERSIONS:
        if profile is not None:
            raise ValueError(f'zuno.profile is only valid with okf_version "{UPSTREAM_OKF_VERSION}" '
                             f"(this document says okf_version {version!r})")
        return version
    if isinstance(version, str) and version == UPSTREAM_OKF_VERSION:
        if isinstance(profile, str) and profile in ZUNO_PROFILES:
            return profile
        raise ValueError(f"unsupported zuno.profile {profile!r} (supported: {', '.join(ZUNO_PROFILES)})")
    raise ValueError(f"unsupported okf_version {version!r} (supported: {supported})")


def at_least_v03(version: str) -> bool:
    """True when the v0.3 rules (skills, models, guardrails, limits, delegation) apply."""
    return LEVEL.get(version, 0) >= LEVEL["v0.3"]


def frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    return (yaml.safe_load(text[4:end]) or {}) if text.startswith("---\n") and end > 0 else {}


def load(policies: pathlib.Path, rel: str) -> dict:
    path = policies / rel
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}


class Corp:
    """The corp policies a bundle is checked against."""

    def __init__(self, policies: pathlib.Path) -> None:
        catalog = load(policies, "models/model-catalog.yaml").get("models") or []
        self.roles: Dict[str, Set[str]] = {}
        for m in catalog:
            self.roles.setdefault(m.get("role", ""), set()).update(m.get("eligible_for") or [])
        guard = load(policies, "guardrails/guardrails-policy.yaml")
        self.modes: List[str] = guard.get("modes") or ["off", "observe", "block"]
        self.min_mode: Dict[str, str] = guard.get("minimum_mode_by_classification") or {}
        self.categories: Set[str] = set(guard.get("categories") or [])
        limits = load(policies, "limits/limits-policy.yaml")
        self.max_tokens: Optional[int] = limits.get("max_tokens")
        self.max_concurrent: Optional[int] = limits.get("max_concurrent_requests")
        self.max_steps: Optional[int] = limits.get("max_steps")
        self.max_tokens_per_turn: Optional[int] = limits.get("max_tokens_per_turn")
        self.max_delegation_depth: Optional[int] = limits.get("max_delegation_depth")
        self.quota_classes: Set[str] = set((load(policies, "quotas/quota-policy.yaml").get("classes") or {}).keys())


def _models(where: str, models: dict, classification: str, corp: Corp) -> List[str]:
    out = []
    preferred = list(models.get("preferred") or [])
    forbidden = list(models.get("forbidden") or [])
    for role in preferred + forbidden:
        if role not in corp.roles:
            out.append(f"{where}: model role {role!r} is not a role of policies/models/model-catalog.yaml")
    for role in preferred:
        if role in corp.roles and classification and classification not in corp.roles[role]:
            out.append(f"{where}: no model of role {role!r} is eligible for {classification} "
                       f"(policies/models/model-catalog.yaml eligible_for)")
    for role in sorted(set(preferred) & set(forbidden)):
        out.append(f"{where}: model role {role!r} is both preferred and forbidden")
    return out


def _limits(where: str, limits: dict, corp: Corp) -> List[str]:
    out = []
    if corp.max_tokens is not None and (limits.get("max_tokens") or 0) > corp.max_tokens:
        out.append(f"{where}: max_tokens {limits['max_tokens']} exceeds the corp ceiling {corp.max_tokens} "
                   f"(policies/limits/limits-policy.yaml)")
    if corp.max_concurrent is not None and (limits.get("max_concurrent_requests") or 0) > corp.max_concurrent:
        out.append(f"{where}: max_concurrent_requests {limits['max_concurrent_requests']} exceeds the corp "
                   f"ceiling {corp.max_concurrent} (policies/limits/limits-policy.yaml)")
    if corp.max_steps is not None and (limits.get("max_steps") or 0) > corp.max_steps:
        out.append(f"{where}: max_steps {limits['max_steps']} exceeds the corp ceiling {corp.max_steps} "
                   f"(policies/limits/limits-policy.yaml)")
    if corp.max_tokens_per_turn is not None and (limits.get("max_tokens_per_turn") or 0) > corp.max_tokens_per_turn:
        out.append(f"{where}: max_tokens_per_turn {limits['max_tokens_per_turn']} exceeds the corp ceiling "
                   f"{corp.max_tokens_per_turn} (policies/limits/limits-policy.yaml)")
    depth = (limits.get("delegation") or {}).get("max_depth")
    if corp.max_delegation_depth is not None and depth is not None and depth > corp.max_delegation_depth:
        out.append(f"{where}: delegation max_depth {depth} exceeds the corp ceiling {corp.max_delegation_depth} "
                   f"(policies/limits/limits-policy.yaml)")
    qc = limits.get("quota_class")
    if qc is not None and qc not in corp.quota_classes:
        out.append(f"{where}: quota_class {qc!r} is not a class of policies/quotas/quota-policy.yaml")
    return out


def _delegation(label: str, bundle: pathlib.Path, z: dict) -> List[str]:
    """ADR-0401: the declared delegation targets exist in the release and are not the agent itself."""
    out: List[str] = []
    name = z.get("name", bundle.name)
    for target in (z.get("delegation") or {}).get("targets") or []:
        agent, task = target.get("agent"), target.get("task")
        if agent == name:
            out.append(f"{label}/agent.okf.md: delegation target {agent!r} is the agent itself")
        elif not (bundle.parent / str(agent) / "agent.okf.md").is_file():
            out.append(f"{label}/agent.okf.md: delegation target agent {agent!r} is not in the release")
        elif not (bundle.parent / str(agent) / "tasks" / f"{task}.md").is_file():
            out.append(f"{label}/agent.okf.md: delegation target task {agent}/{task} does not exist")
    return out


def _skill_path(bundle: pathlib.Path, ref: str, corp_skills: pathlib.Path) -> pathlib.Path:
    if ref.startswith("corp/"):
        return corp_skills / f"{ref[len('corp/'):]}.md"
    return bundle / "skills" / f"{ref}.md"


def check_bundle(bundle: pathlib.Path, corp: Corp, root: pathlib.Path) -> List[str]:
    label = bundle.relative_to(root).as_posix()
    agent = frontmatter(bundle / "agent.okf.md")
    z = agent.get("zuno") or {}
    try:
        version = okf_document_version(agent)
    except ValueError as exc:
        # Fail closed: without a known version this rule cannot tell which checks apply.
        return [f"{label}/agent.okf.md: {exc}"]
    # delegation lives in the agent document: it needs the AGENT to be at v0.3 or above.
    if not at_least_v03(version) and (z.get("delegation") or (z.get("limits") or {}).get("delegation")):
        return [f"{label}/agent.okf.md: delegation is an OKF v0.3 field (profile 1.0 included); this bundle "
                f"declares okf_version {agent.get('okf_version')!r}"]
    # The rules apply when ANY document of the bundle is at v0.3 or above: a legacy v0.2 agent whose tasks are
    # profile 1.0 is narrowed too, since readers accept mixed bundles (ADR-0615 clause 5).
    effective = version
    for task in z.get("tasks") or []:
        task_path = bundle / "tasks" / f"{task}.md"
        if not task_path.is_file():
            continue
        try:
            task_version = okf_document_version(frontmatter(task_path))
        except ValueError:
            continue  # the readers refuse it with a named error
        if at_least_v03(task_version) and not at_least_v03(effective):
            effective = task_version
    if not at_least_v03(effective):
        return []
    classification = (z.get("model") or {}).get("preferred_classification", "")
    findings: List[str] = []

    findings += _models(f"{label}/agent.okf.md", z.get("models") or {}, classification, corp)
    findings += _limits(f"{label}/agent.okf.md", z.get("limits") or {}, corp)
    findings += _delegation(label, bundle, z)

    guard = z.get("guardrails") or {}
    mode = guard.get("mode")
    floor = corp.min_mode.get(classification)
    if mode and floor and corp.modes.index(mode) < corp.modes.index(floor):
        findings.append(f"{label}/agent.okf.md: guardrails mode {mode!r} is weaker than the corp minimum "
                        f"{floor!r} for {classification} (policies/guardrails/guardrails-policy.yaml)")
    for cat in guard.get("categories") or []:
        if cat not in corp.categories:
            findings.append(f"{label}/agent.okf.md: guardrails category {cat!r} is not a corp category "
                            f"(policies/guardrails/guardrails-policy.yaml)")

    for task in z.get("tasks") or []:
        task_path = bundle / "tasks" / f"{task}.md"
        if not task_path.is_file():
            continue  # reported by validate_okf_bundle.py in zuno-demo-agents
        where = f"{label}/tasks/{task}.md"
        tz = frontmatter(task_path).get("zuno") or {}
        findings += _models(where, tz.get("models") or {}, classification, corp)
        task_limits = dict(tz.get("limits") or {})
        for alias in ("max_tokens", "quota_class"):
            if alias in tz:
                task_limits.setdefault(alias, tz[alias])
        findings += _limits(where, task_limits, corp)
        tools, domains = set(tz.get("allowed_tools") or []), set(tz.get("allowed_knowledge") or [])
        for ref in tz.get("skills") or []:
            path = _skill_path(bundle, ref, root / "policies" / "skills")
            if not path.is_file():
                findings.append(f"{where}: skill {ref!r} not found ({path.relative_to(root).as_posix()})")
                continue
            skill = frontmatter(path)
            if skill.get("type") != "skill":
                findings.append(f"{where}: {path.relative_to(root).as_posix()} is not a type: skill document")
                continue
            sz = skill.get("zuno") or {}
            for tool in sorted(set(sz.get("allowed_tools") or []) - tools):
                findings.append(f"{where}: skill {ref!r} needs tool {tool!r}, which the task does not allow")
            for domain in sorted(set(sz.get("allowed_knowledge") or []) - domains):
                findings.append(f"{where}: skill {ref!r} needs knowledge domain {domain!r}, "
                                f"which the task does not allow")
    return findings


def check_release(release: pathlib.Path) -> List[str]:
    corp = Corp(release / "policies")
    findings: List[str] = []
    for agent_md in sorted((release / "agents").glob("*/agent.okf.md")):
        findings += check_bundle(agent_md.parent, corp, release)
    return findings
