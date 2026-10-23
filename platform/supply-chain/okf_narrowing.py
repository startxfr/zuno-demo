"""OKF v0.3 narrowing rule, re-checked at admission (ADR-0579 clause 5, WP-163).

A copy of zuno-demo-agents platform/okf/check_narrowing.py, re-rooted on an
extracted release directory: the rule runs once in the agents repository's
CI and once here, so a misconfigured CI on one side cannot admit a widening
alone. Duplicated on purpose (small, well-specified logic, independent
life cycles - the same convention validate_okf_bundle.py states); keep the
two in step when the rule changes.

Used by admit_okf_bundle.py validate; v0.2 bundles pass trivially.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Set

import yaml

CLASS_ORDER = ["C1", "C2", "C3"]


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
    qc = limits.get("quota_class")
    if qc is not None and qc not in corp.quota_classes:
        out.append(f"{where}: quota_class {qc!r} is not a class of policies/quotas/quota-policy.yaml")
    return out


def _skill_path(bundle: pathlib.Path, ref: str, corp_skills: pathlib.Path) -> pathlib.Path:
    if ref.startswith("corp/"):
        return corp_skills / f"{ref[len('corp/'):]}.md"
    return bundle / "skills" / f"{ref}.md"


def check_bundle(bundle: pathlib.Path, corp: Corp, root: pathlib.Path) -> List[str]:
    label = bundle.relative_to(root).as_posix()
    agent = frontmatter(bundle / "agent.okf.md")
    if agent.get("okf_version") != "v0.3":
        return []
    z = agent.get("zuno") or {}
    classification = (z.get("model") or {}).get("preferred_classification", "")
    findings: List[str] = []

    findings += _models(f"{label}/agent.okf.md", z.get("models") or {}, classification, corp)
    findings += _limits(f"{label}/agent.okf.md", z.get("limits") or {}, corp)

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
            continue  # reported by validate_okf_bundle.py
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
