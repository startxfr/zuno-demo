# Workshop: Agentic AI

## Introduction

Agents are useful only if they can act. On Zuno they act inside the same rules as everyone else. The workshop
follows one agent's working day:
- it answers in a team workspace;
- it calls company tools with the user's rights;
- it reads the user's own documents, and only those;
- it delegates an operation to another agent, and a human approves it.

An operations agent outside UnifAI then uses the same tools under the same rules. The closing block shows where the
agents come from: a signed release, owned by the business, verified by the platform before it starts. Where these
bricks sit in the platform: see [Appendix A](#appendix-a---hld).

**The message:** "Agents act with the user's identity, under the user's rights, through governed tools. They delegate
only when a human approves, and they run only from a signed release."

## Personas

The personas are fictional role accounts of the Keycloak realm `zuno`. They share one password,
kept in Vault at `keycloak/demo-personas`. The [catalogue](../README.md#personas) lists all of them.

| Persona | Profile | Blocks |
|---|---|---|
| **consultant-02** | Consultant and architect, front office. Confluence subgroups, `agent_tekos`, `agent_arkos`, `aap_ops`. | UnifAI agents, MCP tools (the wider tool set), delegation with approval |
| **ai-ops-01** | AI platform operator, back office. `ocp-ai-ops`. | The UnifAI contrast (Tekos with cluster tools), kagent, Grafana and Tempo |
| **sale-01** | Salesperson, front office. `sales`. | The MCP tools contrast, the RAG isolation check |
| **consultant-01** | Consultant and architect, front office. | The live RAG upload |
| **paas-ops-01** | Platform operator, back office. `ocp-paas-ops` (cluster-admin). | The presenter's `oc` terminal, the signed release block |

## Agenda

| Time | Block | Play | Transition to the next block |
|---|---|---|---|
| 0:00 | Opening | The message, then [Appendix A](#appendix-a---hld) on screen | "Let us follow an agent through its day." |
| 0:03 | An agent at work | [UnifAI agents](../scenarios/experiences/unifai-agents.md#5-minute-version), 5-minute version | "An agent that only talks is not much use. It needs tools." |
| 0:08 | Governed tools | [MCP tools by group](../scenarios/governance/mcp-tools-by-group.md#5-minute-version), 5-minute version | "Tools reach company systems. Documents are the other half." |
| 0:13 | My documents | [UnifAI live RAG](../unifai-live-rag.md#5-minute-version), 5-minute version | "Now the agent needs something it cannot do itself." |
| 0:18 | Delegation with approval | [A2A delegation with approval](../scenarios/governance/a2a-delegation-approval.md#15-minute-version), 15-minute version | "Agents can live outside UnifAI too." |
| 0:33 | An operations agent | [kagent](../scenarios/experiences/kagent.md#5-minute-version), 5-minute version | "Where do all these agents come from?" |
| 0:38 | Signed agents | [Signed agent release](../scenarios/foundation/okf-signed-agent-release.md#5-minute-version), 5-minute version | "Last: the agent's own rules about data." |
| 0:46 | Agents carry their data rules (optional) | [Sovereignty](../scenarios/governance/ai-gateway-sovereignty.md#5-minute-version), 5-minute version | |
| 0:51 | Close and questions | Repeat the message | |

## Presenter lifecycle

`make demo use agentic-ai` selects this workshop.
Its actions chain the actions of the scenarios in the agenda (status, check, install and start in agenda order; stop
and uninstall in reverse), then run the workshop's own file. A workshop takes no 5 or 15 version: each block plays the
version its agenda row names. One typed guard, `DEMO_CONFIRM=agentic-ai`, covers the workshop. Each section below says
only what is the workshop's own, or "Nothing to do.".

### Status

Nothing to do. The scenarios' statuses are those of [UnifAI agents](../scenarios/experiences/unifai-agents.md#presenter-lifecycle), [MCP tools by group](../scenarios/governance/mcp-tools-by-group.md#presenter-lifecycle), [UnifAI live RAG](../unifai-live-rag.md#presenter-lifecycle), [A2A delegation with approval](../scenarios/governance/a2a-delegation-approval.md#presenter-lifecycle), [kagent](../scenarios/experiences/kagent.md#presenter-lifecycle), [Signed agent release](../scenarios/foundation/okf-signed-agent-release.md#presenter-lifecycle), [Sovereignty](../scenarios/governance/ai-gateway-sovereignty.md#presenter-lifecycle), in that order.

### Check

The merged probes are `ONLY=unifai-tekos,tools,open-webui,delegation-approval,kagent,sovereignty,trace make demo golden-path`.
The delegation probe can take about 5 minutes when the model retries the tool. The merged browser run covers `unifai`
and `kagent`. All of them must have passed within the last hour. The live RAG and signed release blocks have no probe:
rehearse them the same day. When one block is red, skip that block and say what it would have shown, as
[If something goes wrong](#if-something-goes-wrong) says.

### Install

Nothing to do.

### Start

The scenarios' Start sections already say how to sign in to each product. Only what they share is the workshop's own:

- [ ] One browser profile per persona, signed in before the session: **consultant-02**, **ai-ops-01**, **sale-01** and
  **consultant-01**.
- [ ] In UnifAI, start a separate session per persona in a team workspace. A team session is shared, so
  **consultant-02** could read **ai-ops-01**'s cluster answers.
- [ ] A terminal logged in with `oc` as **paas-ops-01**, which must have signed in to OpenShift once.
- [ ] Grafana and the Tempo search UI, open as **ai-ops-01**.
- [ ] The agents release open in a browser tab:
  [agents/arkos/agent.okf.md](https://github.com/startxfr/zuno-demo-agents/blob/main/agents/arkos/agent.okf.md).
- Every block plays its 5-minute version, except delegation (15-minute version): skip the other "15-minute version"
  items.
- Changing unit: Start of [UnifAI live RAG](../unifai-live-rag.md#presenter-lifecycle) deletes three files from **consultant-01**'s Personal documents and
  uploads two demo files. Run it before the session, not on stage. The single typed guard `DEMO_CONFIRM=agentic-ai`
  covers the workshop, live RAG included.
- The AAP job of the delegation block is launched by you when you click **Approve**. It is read-only and ends by
  itself, as its scenario says.

### Stop

Nothing to do. The scenarios' Stop sections close their browser profiles and terminals. Stop of UnifAI live RAG
deletes the three named files from **consultant-01**'s Personal documents. After its optional Confluence resync, revert
the edit as that page says.

### Uninstall

Nothing to do.

## If time runs short

Drop blocks in this order:
1. sovereignty;
2. the signed release block;
3. kagent.

Keep the delegation block in its 15-minute version: it is the centre of the story.

## If something goes wrong

| Symptom | What to do |
|---|---|
| A block's probe failed in the morning | Skip the block and say what it would have shown. |
| The approval request does not appear on stage | Use the fallback of the [delegation scenario](../scenarios/governance/a2a-delegation-approval.md#if-something-goes-wrong). Show the delegation without the approval step and say so. |
| A second approval request appears | The model retried the tool. Answer it too, or the session waits for the expiry. |
| A block fails on stage | Use the fallback of its scenario page, then move on. Do not debug on stage. |

## Limits

- **The release block shows verification, not a release.** Publishing a new agents release and promoting it is
  owner work: a pull request in the agents repository, a signed build, then a promotion pull request here. It is not
  run on stage.
- **Delegation is shown between two agents only**, Arkos to Tekos. Depth, cycle and budget limits are described, not
  triggered.
- **Not in this workshop:** the other experiences (see the
  [many-experiences workshop](../five-experiences.md)), guardrails and budgets (see the
  [sovereign and governed AI workshop](sovereign-governed-ai.md)).

## Appendix A - HLD

The platform map with every brick of this workshop highlighted: the agent platform, the delegation gateway, the tool
gateway and its servers, the signed release, and the operations agent.

```mermaid
flowchart TB
  subgraph EXP["Experiences: clients of one governed backend"]
    UNIFAI["UnifAI<br/>agents, RAG"]
    OWUI["Open WebUI"]
    CLAW["OpenClaw<br/>one assistant per persona"]
    DIFY["Dify"]
    KAGENT["kagent"]
    LS["OpenShift Lightspeed"]
    BLENDER["Blender add-on"]
    WM["World model"]
  end
  subgraph GOV["Gateways and governance"]
    TP["token proxy,<br/>egress proxy"]
    RHCL["RHCL Kuadrant<br/>auth, rate limits"]
    AIGW["ai-gateway<br/>classification, routing,<br/>guardrails, quotas"]
    MCPGW["mcp-gateway<br/>tools by group"]
    A2A["a2a-gateway<br/>delegation, approval"]
  end
  subgraph AI["Red Hat OpenShift AI"]
    MAAS["MaaS<br/>gateway, portal, API keys"]
    KSERVE["KServe llm-d<br/>local models on MIG GPUs"]
    EXT["SaaS models<br/>Mistral, Codestral, OVHcloud"]
    PG["GenAI playground"]
    BUILD["Pipelines, MLflow,<br/>Kueue, model registry"]
    EVAL["TrustyAI, EvalHub,<br/>LMEval"]
  end
  subgraph TOOLS["Agents and tools"]
    OKF["OKF agents release<br/>zuno-demo-agents"]
    MCPS["MCP servers<br/>Confluence, Git, AAP,<br/>k8s, Google Workspace"]
  end
  subgraph TRUST["Identity, secrets, supply chain"]
    KC["Keycloak<br/>personas, groups"]
    VAULT["Vault, ESO,<br/>cert-manager"]
    SC["RHTAS, Quay,<br/>image policy"]
  end
  subgraph PLAT["Platform and operations"]
    OCP["OpenShift, Service Mesh,<br/>GPU nodes"]
    GITOPS["Argo CD GitOps,<br/>AAP Day 0-3"]
    OBS["Prometheus, Grafana,<br/>Tempo"]
  end
  SAAS[("SaaS<br/>Confluence, Google,<br/>Salesforce")]

  UNIFAI & OWUI & WM --> AIGW
  CLAW & DIFY & KAGENT --> TP --> AIGW
  BLENDER --> RHCL --> AIGW
  UNIFAI --> A2A
  UNIFAI & OWUI & TP & LS --> MCPGW
  LS & PG --> MAAS
  AIGW --> MAAS
  MAAS --> KSERVE
  AIGW --> EXT
  MAAS -. published .-> EXT
  MCPGW --> MCPS --> SAAS
  BUILD --> KSERVE
  EVAL --> MAAS
  RHCL -. limits .-> MAAS
  OKF -. agents, policies .-> UNIFAI & AIGW & MCPGW
  KC -. tokens .-> AIGW & MCPGW & MAAS
  AIGW & MCPGW -. metrics, traces .-> OBS

  classDef focus fill:#ffd54f,stroke:#d84315,stroke-width:4px,color:#000;
  class UNIFAI,A2A,MCPGW,MCPS,OKF,KAGENT focus;
```

## References

The decisions this page rests on:

- [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md): UnifAI is the agent platform.
- [ADR-0011](../../adr/0011-define-tool-authorization-as-policy-intersection.md) and
  [ADR-0036](../../adr/0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md): tool
  authorization is an intersection, enforced in the mcp-gateway.
- [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md),
  [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md) and
  [ADR-0409](../../adr/0409-introduce-human-approval-for-delegated-operations-resumable-from-persisted-checkpoints.md):
  delegation carries the user's identity, is bounded, and waits for a human.
- [ADR-0576](../../adr/0576-extract-agent-definitions-and-corp-policies-into-the-zuno-demo-agents-repository.md),
  [ADR-0578](../../adr/0578-sign-okf-artifacts-keyless-with-github-oidc-and-verify-them-offline-by-identity.md) and
  [ADR-0580](../../adr/0580-consume-the-corp-okf-bundle-by-a-single-digest-pin-promoted-by-pull-request.md): agents
  are released from their own repository, signed, and pinned by digest.
- [ADR-0349](../../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md): Restructure demo personas, ocp-* cluster-access groups and two new agents.
- [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md): Prepare and play every catalogue demo through one make demo lifecycle.

## Page status

> **Status:** Built from seven scenarios, linked in the agenda. Rehearsed as a whole on 2026-11-15 through `make demo
> rehearse agentic-ai`: PASS at 11:49 (96 units, 348 s). Evidence:
> [WP-280](../../roadmap/evidence/wp-280-workshops-rehearsals-2026-11-15.md). Each
> block keeps the status of its scenario page.
> **Show-ready:** only if every probe of its blocks passed within the last hour:
> `ONLY=unifai-tekos,open-webui,tools,delegation-approval,kagent,sovereignty,trace make demo golden-path`. The live RAG
> block has no probe: rehearse it the same day.
> **Duration:** 60 minutes, presenter-led. **Audience:** technical and business; the delegation block plays its
> 15-minute version, the others their 5-minute version.
> **Personas:** see [Personas](#personas).
