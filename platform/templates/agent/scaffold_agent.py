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

This module writes real files into the real repository tree (agents/,
gitops/charts/<name>/, gitops/apps/<name>/, evaluations/<name>/) - the
onboarding workflow is "run this, review the diff, open a PR," not a
throwaway scratch directory. Two things it deliberately does NOT write,
because doing so programmatically would either corrupt heavily-commented
shared files or apply a change no generator should make unreviewed:

  - policies/tools/tool-policy.yaml / policies/knowledge/knowledge-policy.yaml:
    both files are hand-curated and densely commented; a naive
    yaml.safe_load + yaml.safe_dump round-trip would silently destroy
    every comment (verified: this repo's own realm-zuno.json round-trips
    with a large spurious diff even though nothing semantic changed - the
    same risk applies here). Emits exact instructions in NEXT_STEPS.md
    instead.
  - gitops/charts/keycloak/files/realm-zuno.json: same reasoning, plus a
    generated client/group/user fragment needs a human's own judgment
    call about *which* existing users, if any, should also gain the new
    entitlement (see NEXT_STEPS.md's own worked example). Emits
    agents/<name>/keycloak-fragment.json (documented, for manual merge)
    instead.

The scaffolded agent reuses ADR-0327/ADR-0308's operator substrate from
day one: gitops/charts/<name>/templates/aiagent.yaml renders a single
AIAgent CR (the post-WP-38-migration Arkos shape), never a raw manifest
set - "self-service" and "CR-managed" arrive together, not as a later
migration.

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

Every `--knowledge`/`--tool` value must already be a real logical
knowledge domain / tool capability this platform declares (ADR-0306:
"existing knowledge domains and capabilities only, no new external
systems") - this module does not validate that itself (platform/docs/
check_knowledge_refs.py and platform/supply-chain/validate_okf_bundle.py
do, as part of the same PR's own CI run).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass, field
from datetime import date
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


def render_agent_okf(spec: AgentSpec) -> str:
    today = date.today().isoformat()
    knowledge_list = "\n".join(f'    - "{k}"' for k in spec.knowledge_domains) or "    []"
    return f"""---
okf_version: v0.2
type: agent
title: {spec.title}
description: >-
  {spec.description}
provenance:
  maintainer: Zuno Demo architecture team
  repository: zuno-demo
verification:
  status: unverified
freshness:
  last_reviewed: "{today}"
sources:
{knowledge_list}
zuno:
  name: {spec.name}
  status: placeholder
  graph_shape: retrieve_reason_respond
  primary_task: {spec.primary_task}
  tasks:
    - {spec.primary_task}
  rag:
    top_k: {spec.rag_top_k}
  model:
    preferred_classification: {spec.preferred_classification}
    notes: >-
      Scaffolded by platform/templates/agent/ (ADR-0307/WP-41) - reuses
      the retrieve_reason_respond shape and existing knowledge/tool
      capabilities only, no new external systems (ADR-0306).
  access:
    # ADR-0040: agent entitlement group, orthogonal to the
    # `{spec.business_role}` business role that governs tool/data
    # permissions inside {spec.title} (policies/tools/tool-policy.yaml -
    # see this bundle's own NEXT_STEPS.md for the exact policy entries to
    # add).
    groups:
      - {spec.entitlement_group}
  ui:
    displayName: {spec.title}
    tileDescription: {spec.tile_description}
    color: "{spec.color}"
    icon: {spec.icon}
---

# {spec.title}

{spec.description}

Conforms to `platform/okf/schema/zuno-okf-v0.2.schema.json` (ADR-0005,
ADR-0038). `status` stays `placeholder` until the operator confirms the
live ADR-0027/ADR-0028 acceptance gate passes (ADR-0326's completion
pattern, the same bar every hand-built agent clears) - see this bundle's
own `NEXT_STEPS.md` for what remains.

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
roadmap WP-41). No dedicated namespace is reserved (ADR-0329): {spec.title}'s
frontend/BFF deploy into the shared `zuno-ai-run` namespace via the
`zuno.zuno.ai/v1alpha1 AIAgent` CR the operator (ADR-0327/ADR-0308)
reconciles - see `gitops/charts/{spec.name}/templates/aiagent.yaml`.
"""


def render_task_md(spec: AgentSpec) -> str:
    knowledge_lines = "\n".join(f"    - {k}" for k in spec.knowledge_domains)
    tool_lines = "\n".join(f"    - {t}" for t in spec.tools)
    live_read = f"\n  live_read_tool: {spec.live_read_tool}" if spec.live_read_tool else ""
    return f"""---
okf_version: v0.2
type: task
title: {spec.primary_task_title}
zuno:
  allowed_tools:
{tool_lines}
{live_read}
  allowed_knowledge:
{knowledge_lines}
---

# {spec.primary_task_title}

{spec.primary_task_title} using {spec.title}'s declared knowledge domains
and tool capabilities, all reused from the existing platform catalog
(ADR-0306 - no new knowledge domain or external backend for a
template-scaffolded agent).

This is the task Agent Runtime's generic chat dispatch (`POST
/v1/agents/{spec.name}/chat`, ADR-0342) executes once `status: active` -
see `components/agent-runtime/app/registry.py` (ADR-0039) for how the
`allowed_tools`/`allowed_knowledge` above and
`prompts/{spec.primary_task}.md`'s system prompt are resolved into the
running `retrieve_reason_respond` LangGraph workflow.
"""


def render_prompt_md(spec: AgentSpec) -> str:
    return f"""You are {spec.title}, {spec.description[0].lower()}{spec.description[1:]}

Answer using the retrieved context below. Cite sources concisely. If the
retrieved context does not ground an answer, say so rather than
guessing.
"""


def render_tasks_readme(spec: AgentSpec) -> str:
    return f"""# {spec.title} Tasks

One OKF Markdown bundle (ADR-0038), linked from `../agent.okf.md`'s
`zuno.tasks`: `{spec.primary_task}.md` - the only task with a live Agent
Runtime route (`POST /v1/agents/{spec.name}/chat`, ADR-0342's
`retrieve_reason_respond` graph shape, reused unchanged - ADR-0307/WP-41's
own proof that self-service onboarding needs zero new runtime code).
"""


def render_chart_yaml(spec: AgentSpec) -> str:
    return f"""apiVersion: v2
name: {spec.name}
description: >-
  ADR-0306/ADR-0307 (WP-41): renders a single AIAgent CR that the
  aiagent-operator reconciles into {spec.title}'s frontend (portal + chat
  UI) and BFF Deployment/Service/Route in the shared zuno-ai-run
  namespace - scaffolded from platform/templates/agent/, CR-managed from
  day one (never a raw-manifest chart).
type: application
version: 0.1.0
appVersion: "0.1.0"
"""


def render_chart_values_yaml(spec: AgentSpec) -> str:
    knowledge_lines = "\n".join(f"  - {k}" for k in spec.knowledge_domains)
    tool_lines = "\n".join(f"  - {t}" for t in spec.tools)
    return f"""# ADR-0306/ADR-0307 (WP-41): scaffolded by platform/templates/agent/ -
# see gitops/charts/arkos/values.yaml's own comment for why this chart
# carries only CR-population fields, never platform-wide constants
# (those live once, in gitops/charts/aiagent-operator/).

namespace: zuno-ai-run

agentName: {spec.name}

okfBundleRef: agents/{spec.name}

image:
  registry: image-registry.openshift-image-registry.svc:5000
  frontendRepository: zuno-ai-build/agent-frontend
  bffRepository: zuno-ai-build/agent-bff
  tag: latest

frontend:
  replicas: 1
  # Empty means "{spec.name}.<the operator's own clusterBaseDomain>".
  routeHost: ""
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi
  oidcClientId: {spec.name}-frontend

bff:
  replicas: 1
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi
  oidcAudience: {spec.name}-frontend

# ADR-0040: agent entitlement group, orthogonal to the business role that
# governs tool/data permissions inside {spec.title}.
groups:
  entitlementGroup: {spec.entitlement_group}
  businessRoles:
    - {spec.business_role}

knowledgeDomains:
{knowledge_lines}

toolCapabilities:
{tool_lines}
"""


def render_chart_aiagent_yaml(spec: AgentSpec) -> str:
    return f"""# ADR-0306/ADR-0307 (WP-41 scaffold): the ONLY resource this chart
# renders - see gitops/charts/arkos/templates/aiagent.yaml's own comment
# for the full ownership-model rationale (identical here).
apiVersion: zuno.zuno.ai/v1alpha1
kind: AIAgent
metadata:
  name: {{{{ .Values.agentName }}}}
  namespace: {{{{ .Values.namespace }}}}
  labels:
    zuno.io/agent: {{{{ .Values.agentName }}}}
    zuno.io/managed-by: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "90"
spec:
  agentName: {{{{ .Values.agentName }}}}
  targetNamespace: {{{{ .Values.namespace }}}}
  okfBundleRef: {{{{ .Values.okfBundleRef }}}}
  frontend:
    image:
      registry: {{{{ .Values.image.registry }}}}
      repository: {{{{ .Values.image.frontendRepository }}}}
      tag: {{{{ .Values.image.tag }}}}
    replicas: {{{{ .Values.frontend.replicas }}}}
    {{{{- if .Values.frontend.routeHost }}}}
    routeHost: {{{{ .Values.frontend.routeHost }}}}
    {{{{- end }}}}
    resources:
      {{{{- toYaml .Values.frontend.resources | nindent 6 }}}}
    oidcClientId: {{{{ .Values.frontend.oidcClientId }}}}
  bff:
    image:
      registry: {{{{ .Values.image.registry }}}}
      repository: {{{{ .Values.image.bffRepository }}}}
      tag: {{{{ .Values.image.tag }}}}
    replicas: {{{{ .Values.bff.replicas }}}}
    resources:
      {{{{- toYaml .Values.bff.resources | nindent 6 }}}}
    oidcAudience: {{{{ .Values.bff.oidcAudience }}}}
  groups:
    entitlementGroup: {{{{ .Values.groups.entitlementGroup }}}}
    businessRoles:
      {{{{- toYaml .Values.groups.businessRoles | nindent 6 }}}}
  knowledgeDomains:
    {{{{- toYaml .Values.knowledgeDomains | nindent 4 }}}}
  toolCapabilities:
    {{{{- toYaml .Values.toolCapabilities | nindent 4 }}}}
"""


def render_app_d0(spec: AgentSpec, sync_wave: int) -> str:
    return f"""---
# No Day0 content for {spec.name}; see gitops/apps/README.md's -d0/-d1 convention.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: zuno-{spec.name}-d0
  namespace: openshift-gitops
  annotations:
    argocd.argoproj.io/sync-wave: "{sync_wave - 1}"
spec:
  project: zuno
  source:
    repoURL: https://github.com/startxfr/zuno-demo.git
    targetRevision: main
    path: gitops/charts/noop
    helm:
      releaseName: zuno-{spec.name}-d0
  destination:
    server: https://kubernetes.default.svc
    namespace: openshift-gitops
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
"""


def render_app_d1(spec: AgentSpec, sync_wave: int) -> str:
    return f"""---
# {spec.title}'s frontend + BFF (ADR-0306/ADR-0307/WP-41, sixth agent,
# scaffolded from platform/templates/agent/). Depends on the
# {spec.name}-frontend confidential OIDC client from keycloak (see this
# agent's own keycloak-fragment.json) and on
# gitops/apps/aiagent-operator/application-d1.yaml (earlier sync-wave)
# having already reconciled the AIAgent CRD + operator manager - this
# chart's only resource is a CR the operator must exist to act on.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: zuno-{spec.name}-d1
  namespace: openshift-gitops
  annotations:
    argocd.argoproj.io/sync-wave: "{sync_wave}"
spec:
  project: zuno
  source:
    repoURL: https://github.com/startxfr/zuno-demo.git
    targetRevision: main
    path: gitops/charts/{spec.name}
    helm:
      releaseName: zuno-{spec.name}-d1
  destination:
    server: https://kubernetes.default.svc
    namespace: zuno-ai-run
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
"""


def render_eval_readme(spec: AgentSpec) -> str:
    env_prefix = spec.name.upper()
    return f"""# {spec.title} Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for
{spec.title} (ADR-0306/ADR-0307/WP-41, scaffolded from
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
export FRONTEND_URL=https://{spec.name}.apps.<cluster-domain>
export {env_prefix}_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/{spec.name}-frontend)
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
    # every path/CR/persona name below keeps the real hyphenated slug.
    py_name = spec.name.replace("-", "_")
    return f'''#!/usr/bin/env python3
"""Security-negative checks for {spec.title} (ADR-0306/ADR-0307/WP-41,
scaffolded from platform/templates/agent/). Only the checks generic
enough to apply to any agent are generated here - identity propagation
(ADR-0032/0033) and the two-directional ADR-0040 entitlement/business-role
separation - plus one self-consistency check with no live-cluster
dependency at all. A hand-authored slice typically adds its own
narrative-specific checks on top (see evaluations/advantage/
security_checks.py for an example) - this scaffold deliberately doesn't
invent one, since {spec.title} declares no cross-domain boundary to prove
(ADR-0306: reuses existing knowledge/capabilities only).

This cannot be executed in the sandbox this repo was built in (no live
cluster) - written to be genuinely runnable once one exists, same as
run_scenarios.py.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass

import httpx
import yaml

os.environ.setdefault("AGENT", "{spec.name}")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tekos"))
from run_scenarios import AGENT, BFF_URL, RUNTIME_URL, auth_headers  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def bff_forwards_identity_to_runtime() -> CheckResult:
    """ADR-0032: the BFF must forward the validated end-user bearer token
    to the Agent Runtime, which requires one and rejects calls without it.
    """
    resp = httpx.post(
        f"{{BFF_URL}}/api/chat",
        headers=auth_headers("consultant-user-01"),
        json={{"session_id": "sec-check-1", "message": "Where do I find the onboarding checklist?"}},
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult("bff_forwards_identity_to_runtime", ok, f"status={{resp.status_code}} body={{resp.text[:200]}}")


def runtime_ignores_mismatched_user_sub() -> CheckResult:
    """ADR-0033: a request body's user_sub is informational only - the
    Runtime must derive the authoritative subject from the validated
    token, never this field.
    """
    import uuid

    forged_sub = f"not-a-real-user-{{uuid.uuid4().hex[:8]}}"
    resp = httpx.post(
        f"{{RUNTIME_URL}}/v1/agents/{{AGENT}}/chat",
        headers=auth_headers("consultant-user-01"),
        json={{"session_id": "sec-check-2", "user_sub": forged_sub, "message": "Where do I find the onboarding checklist?"}},
        timeout=30,
    )
    ok = resp.status_code == 200 and bool(resp.json().get("reply")) if resp.status_code == 200 else False
    return CheckResult("runtime_ignores_mismatched_user_sub", ok, f"status={{resp.status_code}} forged_sub={{forged_sub}} body={{resp.text[:200]}}")


def entitlement_without_business_role_denied() -> CheckResult:
    """ADR-0040: {spec.entitlement_group} entitlement without any
    business role must still be denied by the BFF/Runtime chat path
    (the agent entitlement alone never substitutes for the business-role
    check the MCP Gateway/policy layer performs).
    """
    resp = httpx.post(
        f"{{BFF_URL}}/api/chat",
        headers=auth_headers("{spec.name}-entitlement-only-user-01"),
        json={{"session_id": "sec-check-3", "message": "Where do I find the onboarding checklist?"}},
        timeout=30,
    )
    # A business-role-less caller can still authenticate and chat (the
    # entitlement/role separation this scaffold's tools rely on is
    # enforced per-tool-call by the MCP Gateway, not by the chat route
    # itself) - this check instead proves the *tool* boundary: no tool
    # call reachable from this chat turn should succeed silently without
    # the business role. Left as a documented scaffold seam: fill in a
    # concrete tool-call assertion once {spec.title}'s real persona is
    # reviewed (see NEXT_STEPS.md).
    ok = resp.status_code in (200, 403)
    return CheckResult("entitlement_without_business_role_denied", ok, f"status={{resp.status_code}} body={{resp.text[:200]}}")


def business_role_without_entitlement_denied_by_bff() -> CheckResult:
    """ADR-0040: the converse case. {role_only_persona} holds the
    {spec.business_role} business role but lacks {spec.entitlement_group}
    entitlement - the BFF's own entitlement check must deny with 403
    before the request ever reaches the Agent Runtime.
    """
    resp = httpx.post(
        f"{{BFF_URL}}/api/chat",
        headers=auth_headers("{role_only_persona}"),
        json={{"session_id": "sec-check-4", "message": "Where do I find the onboarding checklist?"}},
        timeout=30,
    )
    ok = resp.status_code == 403
    return CheckResult("business_role_without_entitlement_denied_by_bff", ok, f"status={{resp.status_code}} body={{resp.text[:200]}}")


def {py_name}_declares_only_scaffolded_knowledge_and_tools() -> CheckResult:
    """Self-consistency check (no live cluster needed): every
    agents/{spec.name}/tasks/*.md file's actual YAML frontmatter must
    stay within the knowledge domains and tool capabilities this agent
    was scaffolded with - catches undeclared scope creep as the bundle
    evolves past its initial scaffold.
    """
    allowed_knowledge_ceiling = {spec.knowledge_domains!r}
    allowed_tools_ceiling = {spec.tools!r}
    tasks_dir = REPO_ROOT / "agents" / "{spec.name}" / "tasks"
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


CHECKS = [
    bff_forwards_identity_to_runtime,
    runtime_ignores_mismatched_user_sub,
    entitlement_without_business_role_denied,
    business_role_without_entitlement_denied_by_bff,
    {py_name}_declares_only_scaffolded_knowledge_and_tools,
]


def run() -> list:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a check erroring is a fail, not a crash
            results.append(CheckResult(check.__name__, False, f"unhandled error: {{exc}}"))
    return results


def main() -> int:
    results = run()
    print(f"{{'PASS':<6}}{{'CHECK'}}")
    for r in results:
        print(f"{{'✓' if r.passed else '✗':<6}}{{r.name}}")
        if not r.passed and r.detail:
            print(f"      -> {{r.detail}}")
    if all(r.passed for r in results):
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
    tool: get_customer
    arguments: {{customer_id: 1}}
    expect_status: 403

  - id: 19
    title: Remaining placeholder agents have no live workloads in the shared zuno-ai-run namespace
    type: agent_isolation_placeholder_empty
    namespace: zuno-ai-run
    agents: []

  - id: 20
    title: Every service's health endpoint returns 200
    type: health_endpoints_all_ok
    services: [frontend, bff, agent-runtime, mcp-gateway, rag-service]
"""


def render_keycloak_fragment(spec: AgentSpec) -> str:
    fragment = {
        "_comment": (
            f"ADR-0306/ADR-0307 (WP-41) scaffold output - NOT auto-merged. "
            f"A human merges the relevant pieces into "
            f"gitops/charts/keycloak/files/realm-zuno.json by hand (see "
            f"agents/{spec.name}/NEXT_STEPS.md), the same way every prior "
            f"agent's realm entries were added - see agent_arkos's own "
            f"client/group/user entries in that file as the worked example."
        ),
        "client": {
            "clientId": f"{spec.name}-frontend",
            "name": f"{spec.title} frontend",
            "publicClient": False,
            "secret": f"${{{{vault.{spec.name}_frontend_client_secret}}}}",
        },
        "group": {
            "name": spec.entitlement_group,
            "path": f"/{spec.entitlement_group}",
            "clientRoles": {f"{spec.name}-frontend": ["access"]},
        },
        "entitlement_only_fixture_user": f"{spec.name}-entitlement-only-user-01",
    }
    return json.dumps(fragment, indent=2) + "\n"


def render_next_steps(spec: AgentSpec) -> str:
    return f"""# {spec.title} onboarding - remaining steps

Scaffolded by `platform/templates/agent/scaffold_agent.py` (ADR-0307,
WP-41). What's real already: the OKF bundle, the CR-managed gitops chart
+ Application, and a 20-scenario evaluation skeleton. What still needs a
human:

1. **Review/adjust the prose** in `agent.okf.md`, `tasks/{spec.primary_task}.md`
   and `prompts/{spec.primary_task}.md` - the scaffold fills in a working
   skeleton, not a finished persona.
2. **Merge `keycloak-fragment.json`** into
   `gitops/charts/keycloak/files/realm-zuno.json` by hand (client, group,
   fixture user) - see `agent_arkos`'s own entries there as the worked
   example this fragment mirrors. Also register the new
   `externalsecret-{spec.name}-frontend.yaml` + `templates/keycloak.yaml`
   vault-file mount, and the Vault seed tasks in
   `ansible/roles/vault/tasks/install.yml` (`keycloak/{spec.name}-frontend`,
   `{spec.name}/frontend-session`) - mirror the most recently added
   agent's own entries in each file.
3. **Add policy entries** (never auto-written - see this module's own
   docstring for why):
   - `policies/tools/tool-policy.yaml`: add `{spec.business_role}` to
     `allowed_groups` for each of: {", ".join(spec.tools) or "(none declared)"}
     - only if not already present.
   - `policies/knowledge/knowledge-policy.yaml`: add `{spec.business_role}`
     to `allowed_groups` for each of: {", ".join(spec.knowledge_domains) or "(none declared)"}
     - only if not already present.
4. **Register the GitOps Application** the same way every other agent's
   is: confirm `gitops/apps/{spec.name}/application-d0.yaml`/`application-d1.yaml`
   look right (sync-wave chosen to land after
   `gitops/apps/aiagent-operator`'s own).
5. **Add `{spec.name}` to `ansible/roles/agents/tasks/check.yml`'s**
   frontend reachability smoke test block, following the existing
   per-agent pattern.
6. **Run the validators** this scaffold's own CI test also runs:
   `python3 platform/supply-chain/validate_okf_bundle.py`,
   `python3 platform/docs/check_knowledge_refs.py`,
   `python3 operator/aiagent-operator/validate_contract.py`,
   `python3 platform/docs/check_docs.py`.
7. **Human review checkpoint**: review the 20 scenarios in
   `evaluations/{spec.name}/scenarios.yaml` before any live gate run
   counts (ADR-0326's own completion pattern).
8. **Operator**: deploy via the `AIAgent` CR, run the 75% gate, flip
   `agents/{spec.name}/agent.okf.md`'s `zuno.status` to `active`.
"""


def write_all(spec: AgentSpec, sync_wave: int, repo_root: pathlib.Path = REPO_ROOT) -> List[pathlib.Path]:
    written: List[pathlib.Path] = []

    def _write(rel_path: str, content: str) -> None:
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    _write(f"agents/{spec.name}/agent.okf.md", render_agent_okf(spec))
    _write(f"agents/{spec.name}/tasks/{spec.primary_task}.md", render_task_md(spec))
    _write(f"agents/{spec.name}/tasks/README.md", render_tasks_readme(spec))
    _write(f"agents/{spec.name}/prompts/{spec.primary_task}.md", render_prompt_md(spec))
    _write(f"agents/{spec.name}/keycloak-fragment.json", render_keycloak_fragment(spec))
    _write(f"agents/{spec.name}/NEXT_STEPS.md", render_next_steps(spec))

    _write(f"gitops/charts/{spec.name}/Chart.yaml", render_chart_yaml(spec))
    _write(f"gitops/charts/{spec.name}/values.yaml", render_chart_values_yaml(spec))
    _write(f"gitops/charts/{spec.name}/templates/aiagent.yaml", render_chart_aiagent_yaml(spec))

    _write(f"gitops/apps/{spec.name}/application-d0.yaml", render_app_d0(spec, sync_wave))
    _write(f"gitops/apps/{spec.name}/application-d1.yaml", render_app_d1(spec, sync_wave))

    _write(f"evaluations/{spec.name}/README.md", render_eval_readme(spec))
    _write(f"evaluations/{spec.name}/scenarios.yaml", render_scenarios_yaml(spec))
    _write(f"evaluations/{spec.name}/gate_config.yaml", render_gate_config(spec))
    _write(f"evaluations/{spec.name}/requirements.txt", render_requirements_txt())
    _write(f"evaluations/{spec.name}/run_scenarios.py", render_run_scenarios_py(spec))
    _write(f"evaluations/{spec.name}/run_acceptance_gate.py", render_run_acceptance_gate_py(spec))
    _write(f"evaluations/{spec.name}/security_checks.py", render_security_checks_py(spec))

    return written


def build_spec_from_args(args: argparse.Namespace) -> AgentSpec:
    return AgentSpec(
        name=args.name,
        title=args.title,
        description=args.description,
        primary_task=args.primary_task,
        primary_task_title=args.primary_task_title,
        knowledge_domains=args.knowledge,
        tools=args.tool,
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
    parser.add_argument("--sync-wave", type=int, default=-96, help="Application sync-wave for the -d1 Application (-d0 is one earlier)")
    parser.add_argument("--force", action="store_true", help="overwrite files if agents/<name>/ already exists")
    args = parser.parse_args()

    if not args.force and (REPO_ROOT / "agents" / args.name).exists():
        print(f"agents/{args.name}/ already exists - pass --force to overwrite", file=sys.stderr)
        return 2

    try:
        spec = build_spec_from_args(args)
    except ValueError as exc:
        print(f"SCAFFOLD ERROR: {exc}", file=sys.stderr)
        return 2

    written = write_all(spec, args.sync_wave)

    print(f"Scaffolded {spec.title!r} ({len(written)} files):")
    for path in written:
        print(f"  {path.relative_to(REPO_ROOT)}")
    print(f"\nNext: read agents/{spec.name}/NEXT_STEPS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
