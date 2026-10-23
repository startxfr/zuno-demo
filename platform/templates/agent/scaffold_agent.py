#!/usr/bin/env python3
"""ADR-0307 (roadmap WP-41 Part A) self-service agent onboarding scaffold.

"A new agent is created from a repository template
(platform/templates/agent/) that scaffolds the OKF bundle skeleton,
AIAgent CR, Keycloak entitlement fragment, policy entries and a
20-scenario evaluation skeleton. A validation workflow (composing the
OKF, knowledge-reference, policy and contract validators) gates the
onboarding PR; a template-created agent reaches `active` through exactly
the same ADR-0326 completion pattern and ADR-0027/0028 gates as the
first five - self-service changes who authors the definition, never the
acceptance bar."

WP-156 (2026-10-23): the AIAgent CR, its chart and Applications, and the
frontend/BFF images are no longer generated - the AIAgent operator,
agent-frontend and agent-bff were retired. An agent is served by UnifAI
(ADR-0561) from its OKF bundle, delivered as a signed OCI release
(ADR-0564, ADR-0580).

WP-165 (ADR-0576 clause 1): the bundle half of this scaffold (agent.okf.md,
tasks, prompts, the Keycloak fragment) and the corp policy entries live in
the zuno-demo-agents repository, which has its own scaffold
(platform/templates/agent/scaffold_agent.py there). What stays here is the
platform half: the evaluation skeleton under evaluations/<name>/, which
UnifAI's scenarios, the acceptance gate and the stresstest run against the
agent once a release carrying it is admitted. The Keycloak entitlement
group is generated from the release (ADR-0581) and reconciled by the
ADR-0530 Job; nothing to merge by hand.

This module writes real files into the real repository tree
(evaluations/<name>/) - the onboarding workflow is "run this, review the
diff, open a PR," not a throwaway scratch directory.

No chart and no Application are generated: UnifAI serves the agent once
its bundle is in an admitted release (the `unifai` Day 2 component deploys
the UnifaiAgentBundle), so onboarding needs no per-agent Kubernetes
manifest.

Usage:

    python3 platform/templates/agent/scaffold_agent.py \\
        --name naveo --title Naveo \\
        --description "Onboarding assistant for new team members." \\
        --primary-task answer-onboarding-question \\
        --primary-task-title "Answer an onboarding question" \\
        --knowledge knowledge.tech --knowledge knowledge.project \\
        --tool search_confluence --tool web_search --tool list_drive_files \\
        --live-read-tool search_confluence \\
        --entitlement-group agent_naveo --business-role consultant \\
        --classification C1 --color "#5C6BC0" --icon compass \\
        --tile-description "New-hire onboarding Q&A, for consultants."

`diagram.generation.create` (ADR-0516, Mermaid diagram rendering) is
added to every scaffolded agent's primary task automatically - it's a
platform-wide default baseline visual capability, not something `--tool`
needs to spell out. Photorealistic image generation
(`image.generation.create`) is NOT a default for the same reason it isn't
default anywhere else in the platform: it's Comage-exclusive, scoped to
marketing visuals - pass `--tool image.generation.create` explicitly only
if a genuinely new agent has that same narrow use case, and update the
corp tool policy's own comment in zuno-demo-agents accordingly.

Every `--knowledge`/`--tool` value must already be a real logical
knowledge domain / tool capability this platform declares (ADR-0410:
"existing knowledge domains and capabilities only, no new external
systems") - this module does not validate that itself; admission of the
release carrying the agent does (`make d3 admit agents`: every tool and
knowledge domain a released agent reaches must be bound here).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass, field
from typing import List, Optional

# platform/templates/agent/scaffold_agent.py -> repo root is 3 levels up
# (parents[0]=agent, parents[1]=templates, parents[2]=platform,
# parents[3]=repo root) - do not confuse with the REPO_ROOT constant
# rendered INTO the generated security_checks.py below, which is
# correctly parents[2] relative to THAT file's own location
# (evaluations/<name>/security_checks.py).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


@dataclass
class AgentSpec:
    name: str
    title: str
    description: str
    primary_task: str
    primary_task_title: str
    knowledge_domains: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    live_read_tool: Optional[str] = None
    entitlement_group: str = ""
    business_role: str = "consultant"
    preferred_classification: str = "C1"
    color: str = "#5C6BC0"
    icon: str = "compass"
    tile_description: str = ""
    rag_top_k: int = 5

    def __post_init__(self) -> None:
        if not self.entitlement_group:
            self.entitlement_group = f"agent_{self.name}"
        if self.live_read_tool and self.live_read_tool not in self.tools:
            raise ValueError(f"--live-read-tool {self.live_read_tool!r} must also be declared with --tool")


def render_eval_readme(spec: AgentSpec) -> str:
    return f"""# {spec.title} Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for
{spec.title} (ADR-0410/ADR-0307/WP-41, scaffolded from
platform/templates/agent/). `run_scenarios.py`/`run_acceptance_gate.py`
here are thin `AGENT={spec.name}` wrappers around the canonical, shared
implementation in `evaluations/tekos/` (ADR-0342); `scenarios.yaml`,
`gate_config.yaml` and `security_checks.py` are this agent's own content
(scaffolded skeleton - review/adjust scenario messages before the human
review checkpoint WP-41 gates on).

**Not yet wired into `make day1|d1 check agents`'s automatic path** -
running this gate against a live cluster requires the human
scenario-review checkpoint. Once that review has happened, the operator
runs it explicitly:

```bash
cd evaluations/{spec.name}
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export UNIFAI_URL=https://unifai-ui-zuno-unifai.apps.<cluster-domain>
export UNIFAI_TEAM_NAME=agent-{spec.name}
export EVAL_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/zuno-evaluations)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
python3 run_acceptance_gate.py     # scenarios + security_checks + gate_checks, one exit code
python3 run_scenarios.py           # just the 20 scenarios
python3 security_checks.py         # just the security-negative checks
```

`AGENT={spec.name}`/`TASK_NAME={spec.primary_task}` are set by the
wrapper scripts automatically.
"""


def render_gate_config(spec: AgentSpec) -> str:
    return f"""# ADR-0107 promotion quality gate configuration for the {spec.name} agent
# (roadmap WP-41, scaffolded from platform/templates/agent/). Consumed by
# evaluations/quality_gate.py. Same 75% default as every other agent
# until evidence suggests otherwise.
scenario_threshold: 0.75
"""


def render_requirements_txt() -> str:
    return "httpx==0.27.2\nPyYAML==6.0.2\n"


def render_run_scenarios_py(spec: AgentSpec) -> str:
    return f'''#!/usr/bin/env python3
"""Thin AGENT={spec.name} wrapper around the canonical, shared
evaluations/tekos/run_scenarios.py (ADR-0342). Sets AGENT (and this
file's own directory takes over as the scenarios.yaml source) before
delegating to its main().

Run directly:

    cd evaluations/{spec.name} && python3 run_scenarios.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("AGENT", "{spec.name}")
os.environ.setdefault("TASK_NAME", "{spec.primary_task}")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))

from run_scenarios import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
'''


def render_run_acceptance_gate_py(spec: AgentSpec) -> str:
    return f'''#!/usr/bin/env python3
"""Thin AGENT={spec.name} wrapper around the canonical, shared
evaluations/tekos/run_acceptance_gate.py (ADR-0342). Combines this
directory's scenarios.yaml/security_checks.py with the shared
run_scenarios.py/gate_checks.py into one gate, one exit code.

NOT wired into the automatic `make day1|d1 check agents` path yet - the
human review checkpoint WP-41's own brief gates on comes first.

Run directly:

    cd evaluations/{spec.name} && python3 run_acceptance_gate.py
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("AGENT", "{spec.name}")
os.environ.setdefault("TASK_NAME", "{spec.primary_task}")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))

from run_acceptance_gate import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
'''


def render_security_checks_py(spec: AgentSpec) -> str:
    role_only_persona = f"{spec.business_role}-role-only-user-01"
    # spec.name is a URL/Kubernetes-style slug (hyphens allowed, e.g.
    # "sixth-agent") - not a valid Python identifier as-is, so the
    # generated check FUNCTION name uses an underscored variant while
    # every path/persona name below keeps the real hyphenated slug.
    py_name = spec.name.replace("-", "_")
    placeholder = f"{spec.name} is a placeholder agent (ADR-0007): it has no UnifAI workflow to chat with"
    return f'''#!/usr/bin/env python3
"""Security-negative checks for {spec.title} (ADR-0410/ADR-0307/WP-41,
scaffolded from platform/templates/agent/). Only the checks generic
enough to apply to any agent are generated here - identity propagation
(ADR-0032/0033) and the two-directional ADR-0040 entitlement/business-role
separation, proven through UnifAI (the only target since WP-156) with the
shared factories of evaluations/common/unifai_checks.py - plus one
self-consistency check with no live-cluster dependency at all. A freshly
scaffolded agent is a placeholder (ADR-0007) with no UnifAI workflow, so
the two checks that need a chat turn are reported as skipped until it is
served; a hand-authored slice typically adds its own narrative-specific
checks on top (see evaluations/advantage/security_checks.py).
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass

import yaml

os.environ.setdefault("AGENT", "{spec.name}")
os.environ.setdefault("TASK_NAME", "{spec.primary_task}")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, MCP_GATEWAY_URL, TASK_NAME, _unifai, auth_headers  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "common"))
import unifai_checks  # noqa: E402
from okf_release import okf_root  # noqa: E402  (WP-165: agents and corp policies)
try:
    from day2_report import log_test_line
except ImportError:
    def log_test_line(*_args, **_kwargs) -> None:
        pass

_LOG_AGENT = AGENT

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False


def {py_name}_declares_only_scaffolded_knowledge_and_tools() -> CheckResult:
    """Self-consistency check (no live cluster needed): every
    agents/{spec.name}/tasks/*.md file of the admitted release must
    stay within the knowledge domains and tool capabilities this agent
    was scaffolded with - catches undeclared scope creep as the bundle
    evolves past its initial scaffold.
    """
    allowed_knowledge_ceiling = {spec.knowledge_domains!r}
    allowed_tools_ceiling = {spec.tools!r}
    tasks_dir = okf_root(REPO_ROOT) / "agents" / "{spec.name}" / "tasks"
    offending = []
    checked = 0
    for task_path in sorted(tasks_dir.glob("*.md")):
        parts = task_path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            continue
        checked += 1
        frontmatter = yaml.safe_load(parts[1]) or {{}}
        zuno = frontmatter.get("zuno") or {{}}
        for domain in zuno.get("allowed_knowledge") or []:
            if domain not in allowed_knowledge_ceiling:
                offending.append(f"{{task_path.name}}: allowed_knowledge includes undeclared {{domain}}")
        for tool in zuno.get("allowed_tools") or []:
            if tool not in allowed_tools_ceiling:
                offending.append(f"{{task_path.name}}: allowed_tools includes undeclared {{tool}}")
    ok = not offending
    return CheckResult(
        "{py_name}_declares_only_scaffolded_knowledge_and_tools",
        ok,
        f"offending={{offending}}" if offending else f"checked {{checked}} task file(s)' frontmatter, all within the scaffolded ceiling",
    )


unifai_forwards_identity_to_the_gateways = unifai_checks.skip(
    CheckResult, "unifai_forwards_identity_to_the_gateways", "{placeholder}",
)
unifai_ignores_a_client_supplied_identity_header = unifai_checks.client_identity_header_refused(CheckResult, _unifai)
business_role_without_entitlement_denied_by_unifai = unifai_checks.entitlement_denied(
    CheckResult, _unifai, agent=AGENT, task=TASK_NAME, persona="{role_only_persona}",
    mcp_gateway_url=MCP_GATEWAY_URL, auth_headers=auth_headers,
)
entitlement_without_business_role_denied = unifai_checks.skip(
    CheckResult, "entitlement_without_business_role_denied", "{placeholder}",
)


CHECKS = [
    unifai_forwards_identity_to_the_gateways,
    unifai_ignores_a_client_supplied_identity_header,
    entitlement_without_business_role_denied,
    business_role_without_entitlement_denied_by_unifai,
    {py_name}_declares_only_scaffolded_knowledge_and_tools,
]


def run() -> list:
    results = []
    for check in CHECKS:
        try:
            result = check()
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            result = CheckResult(check.__name__, False, f"unhandled error: {{exc}}")
        results.append(result)
        log_test_line(_LOG_AGENT, "security", result.name, result.name, result.passed, result.detail)
    return results


def main() -> int:
    results = run()

    print(f"{{'PASS':<6}}{{'CHECK'}}")
    for r in results:
        print(f"{{'-' if r.skipped else '✓' if r.passed else '✗':<6}}{{r.name}}")
        if (not r.passed or r.skipped) and r.detail:
            print(f"      -> {{r.detail}}")

    _unifai().cleanup()
    if all(r.passed for r in results if not r.skipped):
        print("\\nRESULT: PASS")
        return 0
    print("\\nRESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def render_scenarios_yaml(spec: AgentSpec) -> str:
    live_read_scenario = ""
    if spec.live_read_tool:
        live_read_scenario = f"""
  - id: 10
    title: {spec.title} answering a question includes a live-read tool call
    type: chat_triggers_tool
    persona: consultant-user-01
    message: "Where do I find the onboarding checklist?"
    expect_tool: {spec.live_read_tool}
"""
    else:
        live_read_scenario = f"""
  - id: 10
    title: {spec.title} chat handles a follow-up question in the same session
    type: chat_basic_qa
    persona: consultant-user-01
    message: "Can you say more about that?"
"""
    return f"""# {spec.title} acceptance scenarios (ADR-0027: 20 scenarios per agent;
# ADR-0028: 75% pass threshold). Scaffolded by platform/templates/agent/
# (ADR-0307/WP-41) - review and adjust scenario messages/personas before
# the human review checkpoint.
#
# `persona` values are anonymized synthetic usernames from
# gitops/charts/keycloak/files/realm-zuno.json (ADR-0041).
# consultant-user-01 holds both the `{spec.business_role}` business role
# and the `{spec.entitlement_group}` entitlement group.

scenarios:
  - id: 1
    title: Portal loads all six agent tiles
    type: portal_lists_all_agents
    persona: consultant-user-01

  - id: 2
    title: Unauthenticated request to the portal redirects to login
    type: portal_requires_login

  - id: 3
    title: Consultant persona can authenticate and the token carries the expected group claims
    type: keycloak_login
    persona: consultant-user-01
    expect_groups: [{spec.business_role}, {spec.entitlement_group}]

  - id: 4
    title: "{spec.title} tile is enabled for a {spec.business_role}-group, {spec.entitlement_group}-entitled user"
    type: portal_tile_state
    persona: consultant-user-01
    agent: {spec.name}
    expect_enabled: true

  - id: 5
    title: "{spec.title} tile is disabled for a non-entitled user (sales persona)"
    type: portal_tile_state
    persona: sales-user-01
    agent: {spec.name}
    expect_enabled: false

  - id: 6
    title: Placeholder agent tiles (Arkos) show "coming soon" for any user
    type: portal_tile_state
    persona: sales-user-01
    agent: arkos
    expect_enabled: false
    expect_placeholder: true

  - id: 7
    title: "{spec.title} answers a basic question with a grounded reply"
    type: chat_basic_qa
    persona: consultant-user-01
    message: "Where do I find the onboarding checklist?"

  - id: 8
    title: First-token latency is under the 6-second interactive objective
    type: chat_first_token_latency
    persona: consultant-user-01
    message: "Where do I find the onboarding checklist?"
    max_seconds: 6

  - id: 9
    title: Streaming chat emits token events followed by a done event
    type: chat_streaming_sse
    persona: consultant-user-01
    message: "Summarize the onboarding process in one sentence."
{live_read_scenario}
  - id: 11
    title: RAG retrieval contributes at least one citation for a technical topic
    type: rag_retrieval_has_citation
    query: "OpenShift AI model serving NVIDIA L4"

  - id: 12
    title: MCP Gateway denies a tool call outside the caller's allowed groups
    type: mcp_gateway_denied
    persona: sales-user-01
    tool: {spec.tools[0] if spec.tools else "search_confluence"}
    arguments: {{}}
    expect_status: 403

  - id: 13
    title: MCP Gateway returns 404 for an unknown tool name
    type: mcp_gateway_unknown_tool
    persona: consultant-user-01
    tool: does_not_exist
    expect_status: 404

  - id: 14
    title: C3-classified requests fail closed when no SaaS provider is eligible
    type: model_router_fails_closed
    classification: C3

  - id: 15
    title: C1-classified requests try the local model first
    type: model_router_prefers_local
    classification: C1

  - id: 16
    title: BFF rejects a chat request with no bearer token
    type: bff_rejects_missing_jwt

  - id: 17
    title: BFF rejects a JWT with the wrong audience
    type: bff_rejects_wrong_audience
    persona: consultant-user-01

  - id: 18
    title: "MCP Gateway denies a tool {spec.title}'s task doesn't declare (ADR-0036 agent_declaration factor)"
    type: mcp_gateway_denied
    persona: consultant-user-01
    tool: git.repository.delete
    arguments: {{repository: "startx-cloud/zuno-demo"}}
    expect_status: 403

  - id: 19
    title: Remaining placeholder agents have no live workloads in the shared zuno-ai-run namespace
    type: agent_isolation_placeholder_empty
    namespace: zuno-ai-run
    agents: []

  - id: 20
    title: Every service's health endpoint returns 200
    type: health_endpoints_all_ok
    services: [unifai-ui, mcp-gateway, ai-gateway]
"""


def render_next_steps(spec: AgentSpec) -> str:
    return f"""# {spec.title} onboarding - remaining steps

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
WP-41): the 20-scenario evaluation skeleton of this directory. What still
needs a human:

1. **Author the bundle in zuno-demo-agents** (ADR-0576): agent.okf.md,
   `tasks/{spec.primary_task}.md`, `prompts/{spec.primary_task}.md`, the
   entitlement group `{spec.entitlement_group}` and the corp policy
   entries (`{spec.business_role}` allowed for {", ".join(spec.tools) or "(no tool)"} and
   {", ".join(spec.knowledge_domains) or "(no knowledge domain)"}), with that repository's own scaffold.
   Tag a release there.
2. **Admit it here** (ADR-0580): `make d3 admit agents RELEASE=vX.Y.Z
   UPDATE_LOCK=1`, or merge the promotion PR `okf-promote.yml` opens; then
   `python3 platform/okf/generate_stack_config.py` (ADR-0581). The `unifai`
   component deploys its `UnifaiAgentBundle`, the Keycloak reconcile Job
   creates `{spec.entitlement_group}`, and `make d2 check agents` reports
   its availability - no per-agent check entry to add.
3. **Review the scenarios** in `scenarios.yaml` - the scaffold fills in a
   working skeleton, not the agent's real acceptance bar.
4. **Run the validators**: `python3 platform/docs/check_knowledge_refs.py`,
   `python3 platform/docs/check_docs.py`.
5. **Promote** (ADR-0502): follow
   `platform/templates/agent/PROMOTION.md` - the named Stage-1 -> Stage-2
   checklist (scenario review, UnifAI deploy, 75% gate, `zuno.status:
   active` in the agents repository, README update).
"""


def write_all(spec: AgentSpec, repo_root: pathlib.Path = REPO_ROOT) -> List[pathlib.Path]:
    written: List[pathlib.Path] = []

    def _write(rel_path: str, content: str) -> None:
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    _write(f"evaluations/{spec.name}/README.md", render_eval_readme(spec))
    _write(f"evaluations/{spec.name}/scenarios.yaml", render_scenarios_yaml(spec))
    _write(f"evaluations/{spec.name}/gate_config.yaml", render_gate_config(spec))
    _write(f"evaluations/{spec.name}/requirements.txt", render_requirements_txt())
    _write(f"evaluations/{spec.name}/run_scenarios.py", render_run_scenarios_py(spec))
    _write(f"evaluations/{spec.name}/run_acceptance_gate.py", render_run_acceptance_gate_py(spec))
    _write(f"evaluations/{spec.name}/security_checks.py", render_security_checks_py(spec))
    _write(f"evaluations/{spec.name}/NEXT_STEPS.md", render_next_steps(spec))

    return written


_DEFAULT_BASELINE_TOOLS = ["diagram.generation.create"]


def build_spec_from_args(args: argparse.Namespace) -> AgentSpec:
    tools = list(args.tool)
    for default_tool in _DEFAULT_BASELINE_TOOLS:
        if default_tool not in tools:
            tools.append(default_tool)
    return AgentSpec(
        name=args.name,
        title=args.title,
        description=args.description,
        primary_task=args.primary_task,
        primary_task_title=args.primary_task_title,
        knowledge_domains=args.knowledge,
        tools=tools,
        live_read_tool=args.live_read_tool,
        entitlement_group=args.entitlement_group or f"agent_{args.name}",
        business_role=args.business_role,
        preferred_classification=args.classification,
        color=args.color,
        icon=args.icon,
        tile_description=args.tile_description or args.description,
        rag_top_k=args.rag_top_k,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-0307 self-service agent onboarding scaffold")
    parser.add_argument("--name", required=True, help="agent slug, e.g. naveo")
    parser.add_argument("--title", required=True, help="display title, e.g. Naveo")
    parser.add_argument("--description", required=True)
    parser.add_argument("--primary-task", required=True, help="task slug, e.g. answer-onboarding-question")
    parser.add_argument("--primary-task-title", required=True)
    parser.add_argument("--knowledge", action="append", default=[], help="existing knowledge.* domain (repeatable)")
    parser.add_argument("--tool", action="append", default=[], help="existing tool capability (repeatable)")
    parser.add_argument("--live-read-tool", default=None)
    parser.add_argument("--entitlement-group", default=None, help="default: agent_<name>")
    parser.add_argument("--business-role", default="consultant")
    parser.add_argument("--classification", default="C1", choices=["C1", "C2", "C3"])
    parser.add_argument("--color", default="#5C6BC0")
    parser.add_argument("--icon", default="compass")
    parser.add_argument("--tile-description", default=None)
    parser.add_argument("--rag-top-k", type=int, default=5)
    parser.add_argument("--force", action="store_true", help="overwrite files if evaluations/<name>/ already exists")
    args = parser.parse_args()

    if not args.force and (REPO_ROOT / "evaluations" / args.name).exists():
        print(f"evaluations/{args.name}/ already exists - pass --force to overwrite", file=sys.stderr)
        return 2

    try:
        spec = build_spec_from_args(args)
    except ValueError as exc:
        print(f"SCAFFOLD ERROR: {exc}", file=sys.stderr)
        return 2

    written = write_all(spec)

    print(f"Scaffolded {spec.title!r} ({len(written)} files):")
    for path in written:
        print(f"  {path.relative_to(REPO_ROOT)}")
    print(f"\nNext: read evaluations/{spec.name}/NEXT_STEPS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
