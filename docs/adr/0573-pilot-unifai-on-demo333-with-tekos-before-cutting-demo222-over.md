# ADR-0573: Pilot UnifAI on demo333 with Tekos before cutting demo222 over

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0517](0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md), [ADR-0559](0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0569](0569-close-unifai-parity-gaps-generically.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md)

## Context

ADR-0561 replaces the agent layer, and ADR-0568 replaces RAG. Both cut over
the components every demo depends on. `demo222` is the live reference for
demos and webinars. The standing rule is that nothing done for `demo333`
mutates `demo222` (OpenShift objects, `zuno-demo222-*` S3 buckets, Route53,
Vault). ADR-0517 set that rule for the `demo333` rebuild. Before a client demo
on `demo222`, the peer sessions are frozen and the execution chain is
re-proved by running a job, not by reading green CRs. That protocol was
validated on 2026-09-14 before an AAP demo.

`demo333` already runs UnifAI. `unifai-operator` 0.1.12 is installed there
through OLM, from catalog `quay.io/zuno/unifai-operator-catalog:latest` with
automatic approval. It manages two stacks: `unifai-devel` (adopted from the
upstream helmfile, external Keycloak realm `unifai`) and `unifai-olm`. Chat,
RAG ingestion and retrieval were validated there. Any operator image pushed
is rolled out by OLM to both stacks. `demo333` is shared with the Zuno
platform, its nodes were at about 98% of CPU requests, and a dedicated
MachineSet `unifai-worker-a` (two m5a.4xlarge, label `workload=unifai`) was
added for UnifAI. Sources: fork `MEMORY.md` ("Clusters", "UnifAI operator")
and `fork/unifai-operator/README.md`. At the time of writing `demo333` is
powered off. Its current state has not been re-measured for this record.

Three of the eight agents are active: tekos, comage and arkos. The other five
are placeholders. Arkos alone uses `plan_draft_write`, and the rest use
`retrieve_reason_respond` or declare no shape (`agents/*/agent.okf.md`).
Tekos is the original vertical slice. Its primary task
(`agents/tekos/tasks/answer-technical-question.md`) declares
`search_confluence`, `web_search`, `git.repository.read`/`list`,
`diagram.generation.create`, `aap.platform.audit` and `aap.cluster.audit`,
with `knowledge.tech` and `knowledge.project`. Together these exercise RAG,
live MCP tools, classification escalation and project memory in one agent.

ADR-0559 records two facts this record depends on:

- Clusters deploy from `main`, and per-cluster branches are workspaces.
- A command without an explicit `--context` silently answers for `demo222`,
  the shared workstation's current context.

## Decision

**The cutover proceeds in four gated phases. A phase starts only when the
previous one's exit criteria are met, and Zuno code is deleted last.**

**Phase 1: Tekos on `demo333` (WP-154).**

- **Preconditions.** WP-146 to WP-153 are done: identity and context headers
  (ADR-0563), OpenTelemetry (ADR-0566), parity additions (ADR-0569), RAG
  (ADR-0568), OKF bundles (ADR-0564), ArgoCD delivery from a pinned catalog
  (ADR-0574), the MCP north side (ADR-0571) and guardrails in the gateway
  (ADR-0567).
- **Scope.** Tekos as a `UnifaiAgentBundle` in a pilot stack, with Confluence
  RAG through UnifAI, web search, and every MCP tool its task declares,
  through the MCP Gateway with the forwarded JWT.
- **Functional and performance exit criteria.**
  - `evaluations/tekos/` passes against UnifAI's session API at least as well
    as the agent-runtime baseline measured on the same cluster.
  - Scenario `chat_first_token_latency` stays under 6 s.
  - Every **unverified** row of ADR-0561's parity table is resolved: closed
    by ADR-0569, or recorded as an accepted loss.
- **Security exit criteria.**
  - A user without `agent_tekos` cannot use Tekos.
  - A C2 turn never reaches a SaaS provider, checked against ai-gateway
    routing decisions.
  - Another user's session cannot be resumed.
  - A bundle with a broken signature emits nothing.

**Phase 2: the seven other agents on `demo333` (WP-155, first half).** Comage,
arkos, advantage, finage, naveo, soursage and cognos move as bundles. Arkos
is the `plan_draft_write` proof. Placeholders without a shape stay in
`Valid=False` (ADR-0564), and that is an expected outcome, not a failure.
Exit: each active agent passes its own `evaluations/<agent>/` suite, and the
two-agent project-memory scenario (ADR-0209, Tekos then Arkos) passes on
ADR-0569's memory element.

**Phase 3: `demo222` cutover (WP-155, second half).**

- **When.** Only after Phases 1 and 2 are complete, in a window the user
  schedules, and never inside a demo freeze or close enough to one that a
  rollback could not finish before it.
- **Order.** The UnifAI stack is deployed beside the existing agent layer.
  Agents then switch one at a time, Tekos first.
- **Rollback.** Re-enabling the previous Routes and Applications rolls back
  any step. The old agent-runtime, BFF and frontend stay deployable and
  untouched until Phase 4.

**Phase 4: code removal (WP-156).** `components/agent-runtime`,
`agent-bff`, `agent-frontend`, `operator/aiagent-operator`, rag-service,
rag-ingestion and their charts are deleted, and the planned supersessions of
ADR-0561, ADR-0564, ADR-0568 and ADR-0569 are applied. This happens only after
`demo222` has run on UnifAI for a soak period the user approves, including at
least one demo without rollback.

**Isolation rules that hold through Phases 1 and 2.**

1. **No mutation of `demo222`.** Reads are allowed. Every `oc` command passes
   `--context` explicitly (ADR-0559).
2. **Per-cluster enablement.** The `unifai` and `unifai-operator`
   Applications are enabled by a per-cluster Ansible variable, ADR-0559's
   second lever. The variable stays false on `demo222` until Phase 3.
   ArgoCD Applications are applied per cluster, not synced from
   `gitops/apps/`, so a chart merged to `main` does not by itself install
   UnifAI on `demo222`.
3. **Shared charts must keep the old layer working.** Changes to shared
   charts that `demo222` tracks on `main` (ai-gateway for ADR-0567,
   mcp-gateway for ADR-0571) must be backward compatible with the existing
   agent layer and default to off. A merge to `main` that would change
   `demo222` through selfHeal needs explicit human arbitration first.
4. **Pilot stack and operator releases.**
   - **Own namespace.** The pilot runs in its own namespace, not in
     `unifai-devel` or `unifai-olm`.
   - **Pinned catalog.** It is installed from ADR-0574's pinned catalog, not
     `:latest`.
   - **Coordinated releases.** Operator releases during the pilot are
     coordinated with the fork's maintaining session, because OLM rolls an
     operator to every stack on the cluster at once.
5. **Infrastructure needs the user.** Powering `demo333` on, scaling
   `unifai-worker-a` or any other MachineSet, and any node action wait for
   the user's explicit approval.

## Planned supersession

None. This record sequences the cutover. The supersessions it triggers are
declared by ADR-0561, ADR-0564, ADR-0568 and ADR-0569 and applied in Phase 4.

## Consequences

The full replacement is proven on a real cluster with the real eight bundles
before the reference cluster changes. Every regression found costs a
`demo333` iteration, not a demo. The price is time and parallel operation.
Two agent layers coexist on `demo222` through Phase 3, and two code bases are
maintained until Phase 4. Fixes made to agent-runtime in that interval must
be weighed against their throw-away cost.

Running the pilot on the cluster that also hosts the fork's own development
stacks couples the two efforts. An operator release for UnifAI development
lands on the pilot too. Rule 4 contains that coupling but does not remove it.

## Security considerations

The pilot is the first time Zuno identities, Confluence content (C2) and live
MCP tools, including `aap.cluster.audit`, which runs cluster automation, flow
through UnifAI. The pilot stack is therefore never exposed beyond the
namespace, the OpenShift router and the identity Route. The fork's default
charts create unauthenticated public Routes for MongoDB, Qdrant, Redis
Insight and Temporal. The operator removes them unless
`spec.exposure.exposeInternal` is set (`fork/unifai-operator/README.md`). The
pilot keeps that default, and Phase 1 verifies it. `demo333`'s existing
`unifai-devel` stack uses a separate realm with a weak admin password (fork
`MEMORY.md`), so no Zuno credential or C2 content is placed in it.

## Operational considerations

Each phase ends with a written record in its work package: measured
evaluation results, the resolved parity rows, and the security negatives with
the commands used, each with its `--context`. Before Phase 3, and before any
demo during it, the freeze protocol applies. Peer sessions are frozen by
name. The execution chain is re-proved by an end-to-end Tekos chat through
UnifAI, not by reading `UnifaiStack` status, because green status is not
proof that the chain runs.

`demo333` capacity is the pilot's most likely blocker. UnifAI's dev profile
caps requests (`fork/unifai-operator/README.md`), but RAG ingestion of the
Confluence corpus is the heaviest load, and it is scheduled with the user
before it runs.
