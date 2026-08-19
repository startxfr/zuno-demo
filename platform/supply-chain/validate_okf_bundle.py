#!/usr/bin/env python3
"""ADR-0106 OKF bundle validation: schema/structure validity plus policy
reference validity, independent of signature verification
(sign_okf_bundle.py). Deliberately duplicates the small amount of OKF
frontmatter parsing `components/agent-runtime/app/registry.py` and
`components/mcp-gateway/app/agent_declarations.py` already do - this
repository's established convention (see components/agent-bff/README.md's
"Why standard library only") of duplicating small, well-specified parsing
logic across independently deployed services/tools rather than sharing a
module.

Three checks per bundle:

1. **Schema validity** - `agent.okf.md` has `okf_version: v0.2`,
   `type: agent`, `zuno.name` matches the directory name; every task it
   declares has a `tasks/<task>.md` file with `type: task`.
2. **Policy validity** - every tool a task declares in `zuno.allowed_tools`
   resolves against `policies/tools/tool-policy.yaml` (either its legacy
   `tool` name or its ADR-0116 canonical `capability` name - the same
   equivalence WP-01's binding registry/policy evaluation uses, so a
   bundle written with either naming style validates identically).
   `policies/knowledge/knowledge-policy.yaml` (ADR-0202/0203, not yet
   built) is feature-detected: validated the same way once it exists,
   silently skipped until then - this script must not fail on a policy
   layer this repository hasn't built yet.
3. **Content-note cross-reference validity** (ADR-0513) - every `*.md`
   under a bundle's `rag/`, `tools/`, `policies/` has the matching
   `okf_version`/`type`, and its cross-reference back to the bundle's own
   tasks resolves: a `rag/<domain>.md`'s `used_by_tasks` must each declare
   `domain` in their own `zuno.allowed_knowledge`; a `tools/<capability>.md`'s
   `used_by_tasks` must each declare `capability` in their own
   `zuno.allowed_tools`; a `policies/<name>.md`'s `applies_to.tasks` must
   each exist in the bundle, and any `applies_to.tools`/`applies_to.knowledge`
   must each be declared by at least one of those tasks. These three
   directories are documentation only (never an enforcement input, ADR-0513
   Security considerations) - this check only catches drift between the
   note and the tasks it claims to describe, the same spirit as checks 1-2.

Fails closed: an unreadable/malformed bundle, an unknown tool reference, or
a task file that doesn't exist are all reported as findings, never
silently ignored.

Run from the repository root:

    python3 platform/supply-chain/validate_okf_bundle.py [agents/<name> ...]

With no arguments, validates every `agents/*/` bundle.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Dict, List, Set

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
TOOL_POLICY_PATH = REPO_ROOT / "policies" / "tools" / "tool-policy.yaml"
KNOWLEDGE_POLICY_PATH = REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml"


@dataclass
class Finding:
    bundle: str
    message: str


def _split_frontmatter(path: pathlib.Path) -> Dict:
    if not path.is_file():
        raise ValueError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: expected a leading '---' YAML frontmatter block")
    return yaml.safe_load(parts[1]) or {}


def _known_tool_names() -> Set[str]:
    """Every name policies/tools/tool-policy.yaml answers to - legacy
    `tool` names and ADR-0116 canonical `capability` names alike (mirrors
    components/mcp-gateway/app/policy.py's own dual-indexing)."""
    if not TOOL_POLICY_PATH.is_file():
        return set()
    doc = yaml.safe_load(TOOL_POLICY_PATH.read_text()) or {}
    names: Set[str] = set()
    for entry in doc.get("tools", []):
        if "tool" in entry:
            names.add(entry["tool"])
        if "capability" in entry:
            names.add(entry["capability"])
    return names


def _known_knowledge_domains() -> Set[str]:
    """ADR-0202/0203 knowledge policy - feature-detected. Returns an empty
    set (meaning "no knowledge references validated yet") until WP-20
    creates this file; callers must treat an empty set as "skip", not
    "everything is unknown"."""
    if not KNOWLEDGE_POLICY_PATH.is_file():
        return set()
    doc = yaml.safe_load(KNOWLEDGE_POLICY_PATH.read_text()) or {}
    return set(doc.get("domains", {}).keys())


def _content_notes(dir_path: pathlib.Path) -> List[pathlib.Path]:
    """Schema-conformant notes under a rag/tools/policies directory - every
    `*.md` except the directory's own index README (ADR-0513 content is
    one file per item, README.md is the human index, not an item)."""
    if not dir_path.is_dir():
        return []
    return sorted(p for p in dir_path.glob("*.md") if p.name != "README.md")


def _validate_content_notes(bundle_dir: pathlib.Path, label: str, declared_tasks: Dict[str, Dict[str, Set[str]]]) -> List[Finding]:
    """ADR-0513 check 3: rag/tools/policies notes cross-reference tasks the
    bundle actually declares, with the tool/domain those tasks actually
    allow. `declared_tasks` maps task_name -> {"tools": set, "knowledge": set},
    built from the same task frontmatter check 1/2 already parsed."""
    findings: List[Finding] = []

    def _resolve_tasks(rel_path: str, used_by_tasks) -> List[str]:
        unknown = [t for t in used_by_tasks if t not in declared_tasks]
        for t in unknown:
            findings.append(Finding(label, f"{rel_path}: used_by_tasks references '{t}', not a declared task"))
        return [t for t in used_by_tasks if t in declared_tasks]

    for note_path in _content_notes(bundle_dir / "rag"):
        rel = f"rag/{note_path.name}"
        try:
            fm = _split_frontmatter(note_path)
        except ValueError as exc:
            findings.append(Finding(label, str(exc)))
            continue
        if fm.get("okf_version") != "v0.2" or fm.get("type") != "rag":
            findings.append(Finding(label, f"{rel}: expected okf_version v0.2 and type rag"))
            continue
        zuno = fm.get("zuno") or {}
        domain = zuno.get("domain")
        for task_name in _resolve_tasks(rel, zuno.get("used_by_tasks") or []):
            if domain not in declared_tasks[task_name]["knowledge"]:
                findings.append(
                    Finding(label, f"{rel}: domain '{domain}' not in task '{task_name}''s allowed_knowledge")
                )

    for note_path in _content_notes(bundle_dir / "tools"):
        rel = f"tools/{note_path.name}"
        try:
            fm = _split_frontmatter(note_path)
        except ValueError as exc:
            findings.append(Finding(label, str(exc)))
            continue
        if fm.get("okf_version") != "v0.2" or fm.get("type") != "tool":
            findings.append(Finding(label, f"{rel}: expected okf_version v0.2 and type tool"))
            continue
        zuno = fm.get("zuno") or {}
        capability = zuno.get("capability")
        for task_name in _resolve_tasks(rel, zuno.get("used_by_tasks") or []):
            if capability not in declared_tasks[task_name]["tools"]:
                findings.append(
                    Finding(label, f"{rel}: capability '{capability}' not in task '{task_name}''s allowed_tools")
                )

    for note_path in _content_notes(bundle_dir / "policies"):
        rel = f"policies/{note_path.name}"
        try:
            fm = _split_frontmatter(note_path)
        except ValueError as exc:
            findings.append(Finding(label, str(exc)))
            continue
        if fm.get("okf_version") != "v0.2" or fm.get("type") != "policy":
            findings.append(Finding(label, f"{rel}: expected okf_version v0.2 and type policy"))
            continue
        zuno = fm.get("zuno") or {}
        applies_to = zuno.get("applies_to") or {}
        tasks_in_scope = _resolve_tasks(rel, applies_to.get("tasks") or [])
        allowed_tools_union: Set[str] = set()
        allowed_knowledge_union: Set[str] = set()
        for task_name in tasks_in_scope:
            allowed_tools_union |= declared_tasks[task_name]["tools"]
            allowed_knowledge_union |= declared_tasks[task_name]["knowledge"]
        for tool_name in applies_to.get("tools") or []:
            if tool_name not in allowed_tools_union:
                findings.append(
                    Finding(label, f"{rel}: applies_to.tools '{tool_name}' not allowed by any task in applies_to.tasks")
                )
        for domain in applies_to.get("knowledge") or []:
            if domain not in allowed_knowledge_union:
                findings.append(
                    Finding(label, f"{rel}: applies_to.knowledge '{domain}' not allowed by any task in applies_to.tasks")
                )

    return findings


def validate_bundle(bundle_dir: pathlib.Path, known_tools: Set[str], known_domains: Set[str]) -> List[Finding]:
    label = str(bundle_dir.relative_to(REPO_ROOT))
    findings: List[Finding] = []
    index_path = bundle_dir / "agent.okf.md"

    try:
        frontmatter = _split_frontmatter(index_path)
    except ValueError as exc:
        return [Finding(label, str(exc))]

    if frontmatter.get("okf_version") != "v0.2":
        findings.append(Finding(label, f"okf_version must be v0.2, got {frontmatter.get('okf_version')!r}"))
    if frontmatter.get("type") != "agent":
        findings.append(Finding(label, f"type must be 'agent', got {frontmatter.get('type')!r}"))

    zuno = frontmatter.get("zuno") or {}
    if zuno.get("name") != bundle_dir.name:
        findings.append(
            Finding(label, f"zuno.name {zuno.get('name')!r} does not match directory name {bundle_dir.name!r}")
        )

    declared_tasks: Dict[str, Dict[str, Set[str]]] = {}
    for task_name in zuno.get("tasks", []):
        task_path = bundle_dir / "tasks" / f"{task_name}.md"
        try:
            task_frontmatter = _split_frontmatter(task_path)
        except ValueError as exc:
            findings.append(Finding(label, str(exc)))
            continue

        if task_frontmatter.get("type") != "task":
            findings.append(Finding(label, f"{task_path.name}: expected type task"))

        task_zuno = task_frontmatter.get("zuno") or {}
        task_tools = set(task_zuno.get("allowed_tools", []))
        task_knowledge = set(task_zuno.get("allowed_knowledge", []))
        declared_tasks[task_name] = {"tools": task_tools, "knowledge": task_knowledge}

        for tool_name in task_tools:
            if known_tools and tool_name not in known_tools:
                findings.append(
                    Finding(label, f"{task_path.name}: unknown tool '{tool_name}' (not in tool-policy.yaml)")
                )
        for domain in task_knowledge:
            if known_domains and domain not in known_domains:
                findings.append(
                    Finding(label, f"{task_path.name}: unknown knowledge domain '{domain}' (not in knowledge-policy.yaml)")
                )

    findings.extend(_validate_content_notes(bundle_dir, label, declared_tasks))

    return findings


def main() -> int:
    args = sys.argv[1:]
    if args:
        bundle_dirs = [REPO_ROOT / arg for arg in args]
    else:
        bundle_dirs = sorted(p for p in AGENTS_DIR.iterdir() if p.is_dir())

    known_tools = _known_tool_names()
    known_domains = _known_knowledge_domains()

    all_findings: List[Finding] = []
    for bundle_dir in bundle_dirs:
        all_findings.extend(validate_bundle(bundle_dir, known_tools, known_domains))

    print(f"Validated {len(bundle_dirs)} OKF bundle(s) under agents/.")
    if not all_findings:
        print("\nRESULT: PASS - every bundle is structurally valid and every policy reference resolves.")
        return 0

    print(f"\n{len(all_findings)} finding(s):")
    for f in all_findings:
        print(f"  ✗ {f.bundle}: {f.message}")
    print("\nRESULT: FAIL - fix the bundle(s) above (ADR-0106).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
