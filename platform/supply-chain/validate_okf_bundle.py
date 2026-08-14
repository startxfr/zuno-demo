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

Two checks per bundle:

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
        for tool_name in task_zuno.get("allowed_tools", []):
            if known_tools and tool_name not in known_tools:
                findings.append(
                    Finding(label, f"{task_path.name}: unknown tool '{tool_name}' (not in tool-policy.yaml)")
                )
        for domain in task_zuno.get("allowed_knowledge", []):
            if known_domains and domain not in known_domains:
                findings.append(
                    Finding(label, f"{task_path.name}: unknown knowledge domain '{domain}' (not in knowledge-policy.yaml)")
                )

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
