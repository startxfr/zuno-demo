# Demo catalogue

This directory holds the demonstrations of the Zuno platform:

- **Scenarios**: one brick of the platform, or one feature of a brick, per page. Each page has a 5-minute and a
  15-minute version.
- **Workshops**: several scenarios played in order by a presenter, from 30 minutes to 2 hours.
- **Operations documents**: what to check and freeze before showing anything live.

Every scenario page has the same structure. You can open any page and find the same sections in the same place:

| Section | What it gives you |
|---|---|
| Status banner | Date and content of the last read-only check on demo333, whether the page is show-ready ([ADR-0606](../adr/0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md)), workshops that use it |
| Introduction | What the brick is, where it sits in Zuno, the message, the decisions (ADRs) |
| Personas | Each account used or named in the scenario: who it is, what it may do there, and what the presenter does with it |
| Before you start | Accounts (Vault paths, never passwords), URLs, warm-up, known warnings |
| 5-minute version | The message and one visible proof, for any audience: `Time / Do / Say / You should see` |
| 15-minute version | Starts where the 5-minute version stops and shows the mechanism, for a technical audience |
| If something goes wrong | Symptom, fallback, and the sentence to say |
| Limits | What the scenario does not show, and the brick's named limits |
| Appendix A - HLD | The platform map, with the brick highlighted |
| Appendix B - LLD | The brick's internals, drawn from its chart and component |

New pages start from [`_template-scenario.md`](_template-scenario.md).

## Before any live session

1. Run the golden path: `make demo golden-path`, or only the probes of your scenarios with `ONLY=<probe>,<probe> make
   demo golden-path` ([golden-path.md](golden-path.md), [ADR-0605](../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md)).
2. For a demonstration day, apply the [freeze protocol](freeze-protocol.md) and keep the [rollback](rollback.md) page
   open.
3. Read the status banner of every page you will play. A page that says "rehearse before showing" has no golden-path
   probe: rehearse it the same day.

## Status legend

- **Show-ready: yes (probe)**: the experience or feature has a golden-path probe. Show it only if the probe passed
  within the last hour.
- **Rehearse first**: no probe exists. Rehearse the scenario on the day before showing it.
- **Not show-ready**: a named reason prevents it today (for example, the GPU node of the world model is off).
- **Page**:
  - **written**: in the new format;
  - **legacy**: an earlier script, rewritten in the new format in wave 1;
  - **planned (wave N)**: not written yet.

## Scenarios

### Experiences: the clients of one governed backend

| Scenario | Shows | Personas | Golden-path probe | Page |
|---|---|---|---|---|
| [Open WebUI](scenarios/experiences/open-webui.md) | SSO, "Zuno" and "Zuno Code" models, tools by group | sale-01, consultant-02, ai-ops-01 | `open-webui`, `zuno-code` | written (pilot) |
| OpenClaw | One assistant per persona, egress token injection, different tools per persona | consultant-02, sale-01 | `openclaw` | planned (wave 1) |
| Dify | The three pre-imported apps (agent, chatflow, workflow), persona through the token proxy | consultant-02 | `dify` | planned (wave 1) |
| kagent | Cluster diagnosis with read-only tools, a Secret read refused | ai-ops-01 | `kagent` | planned (wave 1) |
| OpenShift Lightspeed | The console assistant served by MaaS | any OpenShift user | `lightspeed` | planned (wave 1) |
| UnifAI agents | Team and Personal workspaces, the Tekos agent | consultant-02, ai-ops-01 | `unifai-tekos` | planned (wave 1) |
| [UnifAI live RAG](unifai-live-rag.md) | Upload, indexing and ACL isolation of documents | consultant-01, sale-01 | none (rehearse first) | legacy |
| [Blender 3D](blender-3d.md) | A sentence becomes editable 3D objects through a local model | ai-dev-01 | `blender` | legacy |
| [World model](world-model.md) | An interactive generated world on an on-demand GPU | ai-ops-01 | `world-model` (not show-ready while its GPU node is off) | legacy |

### Governance of the backend

| Scenario | Shows | Personas | Golden-path probe | Page |
|---|---|---|---|---|
| [Sovereignty by data classification](scenarios/governance/ai-gateway-sovereignty.md) | C1/C2/C3, the C3 floor keeps Arkos on local models, fail closed, the trace | paas-ops-01, ai-ops-01 | `sovereignty`, `trace` | written (pilot) |
| Model routing and fallback | "Zuno Code" to Codestral, preferred and fallback order, fail-fast on unready models | sale-01 | `zuno-code` | planned (wave 2) |
| Guardrails | A prompt injection detected in observe mode, the guardrails dashboard | consultant-02 | `guardrails` | planned (wave 2) |
| One budget per persona | One token budget across all experiences, the stress-test evidence, the per-turn ceiling | sale-01 | none (rehearse first) | planned (wave 2) |
| MCP tools by group | The same question from two personas, two tool sets, one audit | sale-01, consultant-02 | `tools` | planned (wave 2) |
| A2A delegation with approval | Arkos delegates to Tekos, a human approves, expiry | consultant-02 | `delegation-approval` | planned (wave 2) |
| Identity and personas | One identity, groups drive entitlements, negative fixtures | several | none (rehearse first) | planned (wave 2) |

### Red Hat OpenShift AI and models

| Scenario | Shows | Personas | Golden-path probe | Page |
|---|---|---|---|---|
| [MaaS portal and API keys](scenarios/rhoai/maas-portal-api-keys.md) | A self-service key on a group subscription, token limits, revocation | ai-dev-01, ai-ops-01, paas-ops-01 | none (rehearse first) | written (pilot) |
| GenAI playground | The ready-made playground, its MCP tools by group (9 vs 0) | ai-ops-01, ai-dev-01 | none (rehearse first) | planned (wave 3) |
| Model serving with llm-d on MIG | LLMInferenceService, the llm-d router, MIG slices, hardware profiles | presenter terminal | none (rehearse first) | planned (wave 3) |
| External models | Mistral and OVHcloud published through MaaS | presenter terminal | none (rehearse first) | planned (wave 3) |
| Model catalog and registry | The catalog, the registry and the registered adapters | ai-dev-01 | none (rehearse first) | planned (wave 3) |
| LoRA pipeline with MLflow and Kueue | A pipeline run, a TrainJob admitted by Kueue, MLflow tracking | ai-dev-01 | none (rehearse first) | planned (wave 3) |
| Evaluation with TrustyAI and EvalHub | LMEval, EvalHub, the acceptance scenarios per agent | ai-dev-01 | none (rehearse first) | planned (wave 3) |

### Foundation and trust

| Scenario | Shows | Personas | Golden-path probe | Page |
|---|---|---|---|---|
| GitOps and Day 0-3 | `make dN verb component`, Argo CD, drift check, the golden path itself | presenter terminal | none (rehearse first) | planned (wave 4) |
| Signed agent release (OKF) | An agents release signed keyless, admitted by digest, revocation | presenter terminal | none (rehearse first) | planned (wave 4) |
| Image signing and admission | RHTAS, ClusterImagePolicy, the Quay mirror | presenter terminal | none (rehearse first) | planned (wave 4) |
| Vault and PKI | Raft with KMS auto-unseal, ExternalSecrets, certificates | presenter terminal | none (rehearse first) | planned (wave 4) |
| Service mesh and Kiali | mTLS, workload identity, the service graph | paas-ops-01 | none (rehearse first) | planned (wave 4) |
| Observability and traces | The experiences dashboard, a run traced in Tempo, usage and cost | paas-ops-01 | `trace` | planned (wave 4) |
| AAP audited operations | Job templates, audit history read by an agent | paas-ops-01 | none (rehearse first) | planned (wave 4) |

## Workshops (presenter-led)

| Workshop | Built from | Duration | Page |
|---|---|---|---|
| [One backend, three experiences](three-experiences.md) | UnifAI, Open WebUI, OpenClaw, one budget | 30 min | legacy (wave 1) |
| [One governed backend, many experiences](five-experiences.md) | The live experiences, routing, tools, guardrails, the dashboard | 45-60 min | legacy (wave 1) |
| Sovereign and governed AI | Identity, sovereignty, routing, guardrails, budget, trace | about 45 min | planned (wave 2) |
| Agentic AI | UnifAI agents, MCP tools, RAG, delegation with approval, kagent, AAP audit | about 60 min | planned (wave 2) |
| RHOAI end to end | Catalog, serving, external models, MaaS key, playground, LoRA, evaluation | 60-90 min | planned (wave 3) |
| Trusted platform and operations | GitOps, signed release and admission, Vault, mesh, observability, AAP | about 60 min | planned (wave 4) |

**Two-hour combinations:**
- sovereign and governed AI, then agentic AI;
- RHOAI end to end, then the MaaS and sovereignty scenarios in their 15-minute versions;
- trusted platform and operations, then sovereign and governed AI.

Leave 10 minutes for questions between two workshops.

## Personas

The demonstrations sign in with fictional role accounts of the Keycloak realm `zuno`
([ADR-0349](../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md)). They are role names, not
people. They share one password, kept in Vault at `keycloak/demo-personas`; it is never written in these pages.
Groups drive everything a persona can do: which agents it may call, which tools it gets, which model budget it holds,
and what it may see on the cluster. Source of truth: `gitops/charts/keycloak/files/realm-zuno.json`.

| Persona | Profile | Keycloak groups | Used in the demonstrations |
|---|---|---|---|
| **sale-01** | Salesperson, front office | `sales`, `agent_comage`, `agent_finage` | Open WebUI (three tools), OpenClaw (its own assistant, no Confluence), the shared budget, RAG isolation |
| **sale-02** | Salesperson, front office | `sales`, `agent_comage`, `agent_soursage` | not used yet |
| **consultant-01** | Consultant and architect, front office | `consultant` with six Confluence subgroups, `agent_comage`, `agent_tekos`, `agent_arkos`, `agent_naveo`, `aap_admin` | UnifAI live RAG; copied by the probe identity `eval-consultant-01` |
| **consultant-02** | Consultant and architect, front office | `consultant` with Confluence build OpenShift and OpenShift AI and the four architecture spaces, `agent_tekos`, `agent_arkos`, `aap_ops` | UnifAI, Dify, OpenClaw (with Confluence), the Open WebUI contrast, delegation with approval |
| **consultant-03** | Consultant (run), front office | `consultant` with Confluence run OpenShift and Keycloak, `agent_tekos`, `aap_reader` | not used yet |
| **finance-01**, **finance-02** | Finance, middle office | `finance`, `agent_finage` | the tools contrast (Drive and Gmail only) |
| **adv-01**, **adv-02** | Sales administration, middle office | `adv`, `agent_advantage` | not used yet |
| **board-01**, **board-02** | Executive board, back office | `board`, `agent_advantage`, `agent_finage`, `agent_cognos` | not used yet |
| **recrut-01** | Recruiter, back office | `recrut`, `agent_comage`, `agent_soursage` | not used yet |
| **ai-dev-01** | AI developer, back office | `ocp-ai-dev` (edit on the Zuno namespaces), `agent_tekos` | MaaS key, Blender, the playground (no tools) |
| **ai-ops-01** | AI platform operator, back office | `ocp-ai-ops` (admin on the Zuno namespaces), `agent_tekos`, `openwebui_admin` | kagent, Tekos with cluster tools, Grafana and Tempo, the world model, the playground (nine tools) |
| **paas-dev-01** | Platform developer, back office | `ocp-paas-dev` (cluster-reader), `agent_tekos`, `aap_ops` | not used yet |
| **paas-ops-01** | Platform operator, back office | `ocp-paas-ops` (cluster-admin), `agent_tekos`, `aap_admin`, `openwebui_admin` | the presenter's `oc` terminal: probes and cluster-wide checks |

Other identities, never signed in on stage:
- `eval-consultant-01` and the other `eval-*` accounts are copies used by the golden-path probes and the evaluations.
- The `*-entitlement-only-user-01` and `*-role-only-user-01` accounts are negative fixtures for access-denied tests.
- `dify-admin@zuno.local` is Dify's local administrator (Vault `zuno/dify/admin`).
- Some experiences call the platform as a service account that carries exactly the groups of one persona:
  - `service-account-dify` and `service-account-openclaw-consultant-02` act as **consultant-02**;
  - `service-account-openclaw-sale-01` acts as **sale-01**;
  - `service-account-kagent` acts as **ai-ops-01**.

## Operations documents

- [Golden path](golden-path.md): the automated probes and the screens to check before a live session.
- [Freeze protocol](freeze-protocol.md): what stops changing before a demonstration day.
- [Rollback](rollback.md): how to roll back an experience or a gateway.
- [Demo day 2026-11-09](demo-day-2026-11-09.md): the runbook of that day, kept as a record and as an example.
