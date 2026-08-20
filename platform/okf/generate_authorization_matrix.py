#!/usr/bin/env python3
"""ADR-0503 (roadmap WP-44) per-agent authorization matrix generator.

Renders, into each agents/<name>/agent.okf.md body, a generated
`## Authorization matrix` section stating the complete
who x what x for-what x policy intersection for that agent - one row per
(task x tool) and (task x knowledge domain) pair, derived from the
bundle frontmatter plus policies/tools/tool-policy.yaml and
policies/knowledge/knowledge-policy.yaml, plus a `### Model routing`
subsection - one row per task - resolving each task's effective model
chain (reference model + fallback) from platform/ai-gateway/
provider-routing.yaml and policies/model-routing/model-routing-policy.yaml.
The matrix is documentation of the intersection, never an input to it
(ADR-0503 clause 2): MCP Gateway, Agent Runtime, AI Gateway and the
portal keep reading the YAML sources; nothing at runtime reads this
section.

The section lives between HTML comment markers in the Markdown body
(after the closing `---` of the frontmatter), so the three independent
frontmatter parsers (agent-frontend/mcp-gateway/agent-runtime) are
untouched by regeneration. Frontmatter parsing here deliberately
duplicates platform/supply-chain/validate_okf_bundle.py's
_split_frontmatter, per this repo's convention of duplicating small
well-specified parsing code rather than sharing a module.

The quota column renders each task's ADR-0511 class (frontmatter
`zuno.quota_class`, absent = `standard`) with its per-user request
limit from policies/quotas/quota-policy.yaml (WP-54).

Usage (from the repository root):

    python3 platform/okf/generate_authorization_matrix.py             # regenerate all agents
    python3 platform/okf/generate_authorization_matrix.py tekos naveo # only these agents
    python3 platform/okf/generate_authorization_matrix.py --check       # CI: diff committed vs recomputed
    python3 platform/okf/generate_authorization_matrix.py --check --all # CI: additionally require every agent to carry a section
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
TOOL_POLICY_PATH = REPO_ROOT / "policies" / "tools" / "tool-policy.yaml"
KNOWLEDGE_POLICY_PATH = REPO_ROOT / "policies" / "knowledge" / "knowledge-policy.yaml"
QUOTA_POLICY_PATH = REPO_ROOT / "policies" / "quotas" / "quota-policy.yaml"
PROVIDER_ROUTING_PATH = REPO_ROOT / "platform" / "ai-gateway" / "provider-routing.yaml"
MODEL_ROUTING_POLICY_PATH = REPO_ROOT / "policies" / "model-routing" / "model-routing-policy.yaml"

BEGIN_MARKER = ("<!-- BEGIN GENERATED AUTHORIZATION MATRIX (ADR-0503) - do not edit; "
                "regenerate with: python3 platform/okf/generate_authorization_matrix.py -->")
END_MARKER = "<!-- END GENERATED AUTHORIZATION MATRIX -->"


def _split_document(path: pathlib.Path) -> Tuple[Dict, str, str]:
    """Return (frontmatter dict, raw frontmatter text, body text)."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        raise ValueError(f"{path}: expected a leading '---' YAML frontmatter block")
    return yaml.safe_load(parts[1]) or {}, parts[1], parts[2]


def _load_tool_policy() -> Dict[str, Dict]:
    doc = yaml.safe_load(TOOL_POLICY_PATH.read_text(encoding="utf-8")) or {}
    entries: Dict[str, Dict] = {}
    for entry in doc.get("tools") or []:
        for key in ("tool", "capability"):
            name = entry.get(key)
            if name:
                entries.setdefault(name, entry)
    return entries


def _load_knowledge_policy() -> Dict[str, Dict]:
    doc = yaml.safe_load(KNOWLEDGE_POLICY_PATH.read_text(encoding="utf-8")) or {}
    return dict(doc.get("domains") or {})


def _load_quota_classes() -> Dict[str, Dict]:
    doc = yaml.safe_load(QUOTA_POLICY_PATH.read_text(encoding="utf-8")) or {}
    return dict(doc.get("classes") or {})


def _load_providers() -> List[Dict]:
    doc = yaml.safe_load(PROVIDER_ROUTING_PATH.read_text(encoding="utf-8")) or {}
    return list(doc.get("providers") or [])


def _preference_names(entry: Dict) -> List[str]:
    """ADR-0419: mirrors components/ai-gateway/app/model_routing_policy.py's
    own `_preference_names` exactly (duplicated, not imported - this file
    already duplicates validate_okf_bundle.py's frontmatter parsing for the
    same reason: small, well-specified logic, independent lifecycles).
    `preferred:`/`fallback:` take precedence when either is present,
    concatenated in that order; falls back to the single `prefer:` key
    otherwise, unchanged from pre-ADR-0419 behavior."""
    if "preferred" in entry or "fallback" in entry:
        return list(entry.get("preferred") or []) + list(entry.get("fallback") or [])
    return list(entry.get("prefer") or [])


def _load_model_routing() -> Tuple[Dict[Tuple[str, str], List[str]], Dict[Tuple[str, str], str]]:
    doc = yaml.safe_load(MODEL_ROUTING_POLICY_PATH.read_text(encoding="utf-8")) or {}
    preferences: Dict[Tuple[str, str], List[str]] = {}
    for entry in doc.get("preferences") or []:
        preferences[(entry["agent"], entry["task"])] = _preference_names(entry)
    adapters: Dict[Tuple[str, str], str] = {}
    for entry in doc.get("adapters") or []:
        adapters[(entry["agent"], entry["task"])] = entry.get("adapter", "?")
    return preferences, adapters


def _effective_model_chain(
    classification: str, providers: List[Dict], prefer: List[str], local_only: bool = False
) -> List[str]:
    """Mirrors components/ai-gateway/app/routing.py's
    RoutingTable.candidates_for() + _apply_preference(): filter providers
    eligible for `classification`, keep provider-routing.yaml's order,
    then move any `prefer` names that survived to the front in that order
    - a pure reorder, never able to resurrect a provider eligibility
    filtered out. Duplicated here rather than imported (this file already
    duplicates validate_okf_bundle.py's frontmatter parsing for the same
    reason: small, well-specified logic, independent lifecycles).

    `local_only` (ADR-0416, `zuno.model.local_only`) mirrors routing.py's
    own source-level restriction: when set, non-local candidates are
    dropped regardless of classification eligibility - without this, an
    agent like Finage would show openai/anthropic as "reference"/fallback
    candidates in this generated table even though local_only makes them
    unreachable at runtime, which would make the doc actively wrong."""
    known = {p["name"] for p in providers}
    candidates = [
        p["name"]
        for p in providers
        if classification in (p.get("eligible_for") or [])
        and (not local_only or p.get("kind") == "local")
    ]
    deduped = [name for name in dict.fromkeys(prefer) if name in known]
    preferred = [name for name in deduped if name in candidates]
    rest = [name for name in candidates if name not in deduped]
    return preferred + rest


def _quota_cell(task_zuno: Dict, quota_classes: Dict[str, Dict]) -> str:
    cls_name = task_zuno.get("quota_class") or "standard"
    cls = quota_classes.get(cls_name) or {}
    user_req = (cls.get("requests") or {}).get("user") or {}
    if user_req.get("limit"):
        return f"`{cls_name}` (user {user_req['limit']} req/{user_req.get('window', '?')})"
    return f"`{cls_name}`"


def _groups_cell(allowed_groups: List[str]) -> str:
    if not allowed_groups:
        return "(no groups — unusable)"
    return ", ".join(allowed_groups)


def _render_section(agent_dir: pathlib.Path, tool_policy: Dict[str, Dict],
                    knowledge_policy: Dict[str, Dict], quota_classes: Dict[str, Dict],
                    providers: List[Dict], model_preferences: Dict[Tuple[str, str], List[str]],
                    model_adapters: Dict[Tuple[str, str], str]) -> str:
    frontmatter, _, _ = _split_document(agent_dir / "agent.okf.md")
    zuno = frontmatter.get("zuno") or {}
    name = zuno.get("name", agent_dir.name)
    access_groups = (zuno.get("access") or {}).get("groups") or []
    model_zuno = zuno.get("model") or {}
    classification = model_zuno.get("preferred_classification", "?")
    local_only = bool(model_zuno.get("local_only", False))
    primary_task = zuno.get("primary_task")
    tasks: List[str] = zuno.get("tasks") or []

    lines: List[str] = []
    lines.append(BEGIN_MARKER)
    lines.append("")
    lines.append("## Authorization matrix")
    lines.append("")
    lines.append(
        f"Generated per ADR-0503 from this bundle's frontmatter, "
        f"`policies/tools/tool-policy.yaml`, "
        f"`policies/knowledge/knowledge-policy.yaml`, "
        f"`platform/ai-gateway/provider-routing.yaml` and "
        f"`policies/model-routing/model-routing-policy.yaml` — the enforced "
        f"intersection (ADR-0011/ADR-0203) restated for review, never read "
        f"at runtime. Entitlement (ADR-0040): `{', '.join(access_groups) or '(none)'}`; "
        f"model classification ceiling (ADR-0021): `{classification}`; "
        f"status: `{zuno.get('status', '?')}`"
        + (f"; local-only (ADR-0416): `{str(local_only).lower()}`" if local_only else "")
        + "."
    )
    lines.append("")

    rows: List[str] = []
    task_labels: List[Tuple[str, str]] = []
    for task_name in tasks:
        task_path = agent_dir / "tasks" / f"{task_name}.md"
        if not task_path.is_file():
            raise ValueError(f"{name}: zuno.tasks names {task_name!r} but {task_path} is missing")
        task_fm, _, _ = _split_document(task_path)
        task_zuno = task_fm.get("zuno") or {}
        live_read = task_zuno.get("live_read_tool")
        task_label = f"`{task_name}`"
        flags = []
        if task_name == primary_task:
            flags.append("primary")
        prompt_path = agent_dir / "prompts" / f"{task_name}.md"
        if prompt_path.is_file():
            flags.append(f"prompt: `prompts/{task_name}.md`")
        if flags:
            task_label += f" ({'; '.join(flags)})"
        task_labels.append((task_name, task_label))

        for tool_name in task_zuno.get("allowed_tools") or []:
            entry = tool_policy.get(tool_name)
            if entry is None:
                raise ValueError(f"{name}/{task_name}: tool {tool_name!r} not in tool-policy.yaml")
            ext = entry.get("external_model_policy") or {}
            ext_cell = "blocked" if ext.get("allow_context") is False else "allowed"
            tool_cell = f"`{tool_name}`" + (" (live-read)" if tool_name == live_read else "")
            rows.append(
                f"| {task_label} | {tool_cell} | tool | "
                f"`{entry.get('capability', tool_name)}` @ {entry.get('mcp_server', '?')} | "
                f"{entry.get('min_classification', '?')} | "
                f"{_groups_cell(entry.get('allowed_groups') or [])} | {ext_cell} | "
                f"{_quota_cell(task_zuno, quota_classes)} | `tools/tool-policy.yaml` `{entry.get('tool', tool_name)}` |"
            )

        for domain in task_zuno.get("allowed_knowledge") or []:
            entry = knowledge_policy.get(domain)
            if entry is None:
                raise ValueError(f"{name}/{task_name}: domain {domain!r} not in knowledge-policy.yaml")
            rows.append(
                f"| {task_label} | `{domain}` | knowledge | — | "
                f"{entry.get('min_classification', '—')} | "
                f"{_groups_cell(entry.get('allowed_groups') or [])} | — | "
                f"{_quota_cell(task_zuno, quota_classes)} | `knowledge/knowledge-policy.yaml` `{domain}` |"
            )

    if rows:
        lines.append("| Task (FOR WHAT) | Resource (WHAT) | Kind | Capability / server | Min class | Business roles (WHO) | Ext-model context | Quota | Policy source |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        lines.extend(rows)
    else:
        lines.append(
            "No capabilities declared: every task's `allowed_tools`/"
            "`allowed_knowledge` is empty, so this agent can invoke no tool "
            "and retrieve from no knowledge domain regardless of caller "
            "groups (the honest Stage-1 zero-capability state, ADR-0502)."
        )

    if task_labels:
        lines.append("")
        lines.append("### Model routing")
        lines.append("")
        lines.append(
            "Effective per-task model chain (ADR-0021/ADR-0303/ADR-0412), resolved "
            "from `platform/ai-gateway/provider-routing.yaml`'s classification "
            "eligibility reordered by this `(agent, task)`'s `policies/model-routing/"
            "model-routing-policy.yaml` preference — the first entry is the "
            "reference model, the rest are fallback alternatives, in try order."
        )
        lines.append("")
        lines.append("| Task | Classification ceiling | Reference model | Fallback chain | Adapter | Policy source |")
        lines.append("|---|---|---|---|---|---|")
        for task_name, task_label in task_labels:
            if classification not in ("C1", "C2", "C3"):
                lines.append(f"| {task_label} | `{classification}` | — | (classification ceiling unknown — cannot resolve) | — | — |")
                continue
            prefer = model_preferences.get((name, task_name), [])
            chain = _effective_model_chain(classification, providers, prefer, local_only=local_only)
            reference = f"`{chain[0]}`" if chain else "(none eligible)"
            fallback = ", ".join(f"`{p}`" for p in chain[1:]) or "—"
            adapter = model_adapters.get((name, task_name))
            adapter_cell = f"`{adapter}`" if adapter else "—"
            lines.append(
                f"| {task_label} | `{classification}` | {reference} | {fallback} | {adapter_cell} | "
                f"`policies/model-routing/model-routing-policy.yaml` |"
            )

    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def _current_section(body: str) -> Optional[str]:
    start = body.find(BEGIN_MARKER)
    if start == -1:
        return None
    end = body.find(END_MARKER, start)
    if end == -1:
        raise ValueError("BEGIN marker present without END marker")
    return body[start:end + len(END_MARKER)]


def _agent_dirs(only: List[str]) -> List[pathlib.Path]:
    dirs = sorted(p for p in AGENTS_DIR.iterdir() if (p / "agent.okf.md").is_file())
    if only:
        dirs = [d for d in dirs if d.name in only]
        missing = set(only) - {d.name for d in dirs}
        if missing:
            raise SystemExit(f"unknown agent(s): {', '.join(sorted(missing))}")
    return dirs


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0503 authorization matrix generator")
    parser.add_argument("agents", nargs="*", help="agent names (default: all)")
    parser.add_argument("--check", action="store_true",
                        help="verify committed sections match regeneration; never writes")
    parser.add_argument("--all", action="store_true",
                        help="with --check: also fail for agents carrying no section at all")
    args = parser.parse_args()

    tool_policy = _load_tool_policy()
    knowledge_policy = _load_knowledge_policy()
    quota_classes = _load_quota_classes()
    providers = _load_providers()
    model_preferences, model_adapters = _load_model_routing()

    failures: List[str] = []
    written: List[str] = []
    for agent_dir in _agent_dirs(args.agents):
        index_path = agent_dir / "agent.okf.md"
        _, frontmatter_text, body = _split_document(index_path)
        expected = _render_section(agent_dir, tool_policy, knowledge_policy, quota_classes,
                                   providers, model_preferences, model_adapters)
        current = _current_section(body)

        if args.check:
            if current is None:
                if args.all:
                    failures.append(f"{agent_dir.name}: no authorization matrix section (run the generator)")
                continue
            if current != expected:
                failures.append(f"{agent_dir.name}: committed matrix differs from regeneration (run the generator)")
            continue

        if current is None:
            new_body = body.rstrip() + "\n\n" + expected + "\n"
        elif current == expected:
            continue
        else:
            new_body = body.replace(current, expected)
        index_path.write_text(f"---{frontmatter_text}---{new_body}", encoding="utf-8")
        written.append(agent_dir.name)

    if args.check:
        if failures:
            print(f"{len(failures)} authorization-matrix drift issue(s):")
            for f in failures:
                print(f"  ✗ {f}")
            print("\nRESULT: FAIL - regenerate with python3 platform/okf/generate_authorization_matrix.py (ADR-0503).")
            return 1
        print("RESULT: PASS - every committed authorization matrix matches regeneration.")
        return 0

    print(f"Regenerated {len(written)} matrix section(s): {', '.join(written) or '(none - all current)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
