# Workshop: Trusted platform and operations

## Introduction

An AI platform is only as trustworthy as the platform under it. This workshop shows the foundations that the other
workshops take for granted:
- everything is declared in Git and applied the same way every time;
- every image and every agents release that runs is signed and verified;
- no application holds a static secret;
- traffic between services is encrypted and identified;
- every request can be traced;
- operations are audited.

Each block shows one of these foundations on the live cluster, mostly from the presenter's terminal and from read-only
screens. Where these bricks sit in the platform: see [Appendix A](#appendix-a---hld).

**The message:** "What runs is declared, signed and verified. Secrets come from Vault, traffic is encrypted, and every
request and operation leaves a trace. The platform can show this, not just claim it."

## Personas

The personas are fictional role accounts of the Keycloak realm `zuno`. They share one password,
kept in Vault at `keycloak/demo-personas`. The [catalogue](../README.md#personas) lists all of them.

| Persona | Profile | Blocks |
|---|---|---|
| **paas-ops-01** | Platform operator, back office. `ocp-paas-ops` (cluster-admin), `aap_admin`. | The presenter's `oc` terminal in every block |
| **ai-ops-01** | AI platform operator, back office. `ocp-ai-ops` (admin on the Zuno namespaces). | Grafana, Tempo and the mesh dashboards |
| **consultant-02** | Consultant, front office. `aap_ops`. | The AAP block. Its chat in UnifAI also produces the run traced in the observability block. |
| **consultant-03** | Consultant (run), front office. `aap_reader`. | The AAP contrast: same screen, read-only rights |

The scenario pages name a few more accounts; their Personas sections say which.

## Agenda

| Time | Block | Play | Transition to the next block |
|---|---|---|---|
| 0:00 | Opening | The message, then [Appendix A](#appendix-a---hld) on screen | "Everything starts in Git." |
| 0:03 | Declared | [GitOps and Day 0-3](../scenarios/foundation/gitops-day0-3.md#5-minute-version), 5-minute version | "What Git declares must be what actually runs. That is what signatures prove." |
| 0:08 | Signed images | [Image signing and admission](../scenarios/foundation/image-signing-admission.md#5-minute-version), 5-minute version | "Images are signed. Agents are too." |
| 0:13 | Signed agents | [Signed agent release](../scenarios/foundation/okf-signed-agent-release.md#5-minute-version), 5-minute version | "Signed code still needs credentials. None of them live in the code." |
| 0:18 | No static secrets | [Vault and PKI](../scenarios/foundation/vault-pki.md#5-minute-version), 5-minute version | "Secrets are safe at rest. In transit, the mesh protects the traffic." |
| 0:23 | Encrypted traffic | [Service mesh and Kiali](../scenarios/foundation/service-mesh-kiali.md#5-minute-version), 5-minute version | "Encrypted traffic is also observed traffic." |
| 0:28 | Observed | [Observability and traces](../scenarios/foundation/observability-trace.md#15-minute-version), 15-minute version | "Last foundation: the operations themselves are audited." |
| 0:43 | Audited | [AAP audited operations](../scenarios/foundation/aap-audited-operations.md#5-minute-version), 5-minute version | |
| 0:48 | Close and questions | Repeat the message | |

For a two-hour session, follow this workshop with the [sovereign and governed AI workshop](sovereign-governed-ai.md):
the foundations first, then the AI controls built on them.

## Presenter lifecycle

`make demo use trusted-platform-ops` selects this workshop.
Its actions chain the actions of the scenarios in the agenda (status, check, install and start in agenda order; stop
and uninstall in reverse), then run the workshop's own file. A workshop takes no 5 or 15 version: each block plays the
version its agenda row names. One typed guard, `DEMO_CONFIRM=trusted-platform-ops`, covers the workshop. Each section below says
only what is the workshop's own, or "Nothing to do.".

### Status

Nothing to do. The scenarios' statuses are those of [GitOps and Day 0-3](../scenarios/foundation/gitops-day0-3.md#presenter-lifecycle), [Image signing and admission](../scenarios/foundation/image-signing-admission.md#presenter-lifecycle), [Signed agent release](../scenarios/foundation/okf-signed-agent-release.md#presenter-lifecycle), [Vault and PKI](../scenarios/foundation/vault-pki.md#presenter-lifecycle), [Service mesh and Kiali](../scenarios/foundation/service-mesh-kiali.md#presenter-lifecycle), [Observability and traces](../scenarios/foundation/observability-trace.md#presenter-lifecycle), [AAP audited operations](../scenarios/foundation/aap-audited-operations.md#presenter-lifecycle), in that order.

### Check

The merged probes are `ONLY=unifai-tekos,trace make demo golden-path`, from the observability block. There is no
browser check. `make demo golden-path` must have passed within the last hour. Every other block has no probe:
rehearse it the same day. When one block is red, skip that block and say what it would have shown, as
[If something goes wrong](#if-something-goes-wrong) says.

### Install

Nothing to do.

### Start

The scenarios' Start sections already say how to sign in to each product. Only what they share is the workshop's own:

- [ ] A terminal at the repository root, logged in with `oc` as **paas-ops-01**. The persona must have signed in to
  OpenShift once, because its OpenShift group is created at first sign-in. Use a large font and a dark background.
- [ ] Sign in to Grafana, the Tempo search UI and Kiali as **ai-ops-01**.
- [ ] Open the AAP console in two browser profiles, **consultant-02** and **consultant-03**.
- [ ] Have a UnifAI chat of **consultant-02** with Tekos run during the session, so that the observability block
  finds a recent trace.
- [ ] On stage, run only the read-only commands the pages give. Releases, signatures, rollouts and job launches are
  rehearsal-only, with the platform owner's go.
- Every block plays its 5-minute version, except observability (15-minute version): skip the other "15-minute
  version" items.
- Changing units: Start of [Service mesh and Kiali](../scenarios/foundation/service-mesh-kiali.md#presenter-lifecycle) runs `make demo golden-path` to create traffic, in the hour
  before the session. Start of [AAP audited operations](../scenarios/foundation/aap-audited-operations.md#presenter-lifecycle) launches one read-only AAP job,
  `zuno-day0-check`, which takes several minutes. The single typed guard `DEMO_CONFIRM=trusted-platform-ops` covers the
  workshop, both included.

### Stop

Nothing to do. The scenarios' Stop sections close their browser profiles, tabs and terminals. The AAP job ends by
itself: its pod disappears and its record stays.

### Uninstall

Nothing to do.

## If time runs short

Play the observability block in its 5-minute version. Then drop the mesh block. Keep GitOps, the two signature blocks
and Vault: together they are the trust story.

## If something goes wrong

| Symptom | What to do |
|---|---|
| A command answers slowly or with an authentication error | The API server may be under load. Wait a few seconds and run it again once. If it fails again, show the next block from its page and say so. |
| A block's screen does not load (Grafana, Kiali, AAP) | Show the terminal steps of the same block instead. Each page gives them. |
| A block fails on stage | Use the fallback of its scenario page, then move on. Do not debug on stage. |

## Limits

- **Nothing is changed on stage.** No release is published, no image signed, no secret rotated, no job launched. The
  pages describe these changes and give their evidence; doing them live is rehearsal work.
- **Only one block has a golden-path probe.** Rehearsal is the check for the others.
- **The AI controls on top of this foundation are shown elsewhere:** see the
  [sovereign and governed AI workshop](sovereign-governed-ai.md) and the [agentic AI workshop](agentic-ai.md).

## Appendix A - HLD

The platform map with every brick of this workshop highlighted: GitOps and AAP, the supply chain, the signed agents
release, Vault, the platform and its mesh, and observability.

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
  class GITOPS,SC,OKF,VAULT,OCP,OBS focus;
```

## References

The decisions this page rests on:

- [ADR-0060](../../adr/0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md) and
  [ADR-0605](../../adr/0605-gate-every-live-demo-on-a-golden-path-check-and-a-freeze-window.md): a Day 0-3 contract,
  and a golden-path check before any live demonstration.
- [ADR-0115](../../adr/0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) and
  [ADR-0535](../../adr/0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md): immutable, signed and
  verifiable artifacts, with RHTAS.
- [ADR-0024](../../adr/0024-use-vault-for-application-secrets.md) and
  [ADR-0211](../../adr/0211-publicly-trusted-wildcard-tls-via-lets-encrypt-and-route53.md): Vault for secrets, publicly
  trusted certificates.
- [ADR-0037](../../adr/0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md): network and
  workload identity boundaries.
- [ADR-0029](../../adr/0029-instrument-model-usage-costs-and-distributed-traces.md): usage, cost and distributed
  traces.
- [ADR-0354](../../adr/0354-add-ansible-automation-platform-as-a-day-1-component.md) and
  [ADR-0355](../../adr/0355-expose-aap-audits-to-agents-through-an-mcp-aap-server.md): audited operations with AAP.
- [ADR-0602](../../adr/0602-harden-the-platform-trust-boundaries-before-a-customer-runs-it.md): the hardening of the
  trust boundaries.
- [ADR-0349](../../adr/0349-restructure-demo-personas-cluster-access-groups-and-new-agents.md): Restructure demo personas, ocp-* cluster-access groups and two new agents.
- [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md): Prepare and play every catalogue demo through one make demo lifecycle.

## Page status

> **Status:** Built from seven scenarios, linked in the agenda. Rehearsed as a whole on 2026-11-15 through `make demo
> rehearse trusted-platform-ops`: PASS at 11:38 (94 units, 725 s). Evidence:
> [WP-280](../../roadmap/evidence/wp-280-workshops-rehearsals-2026-11-15.md). Each block keeps the status of
> its scenario page.
> **Show-ready:** only the observability block has a golden-path probe (`trace`). Run `make demo golden-path` before the
> session, and rehearse every other block the same day.
> **Duration:** 60 minutes, presenter-led. **Audience:** platform, security and operations teams; the observability
> block plays its 15-minute version, the others their 5-minute version.
> **Personas:** see [Personas](#personas).
