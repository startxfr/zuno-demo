# ADR-0572: Scope the zuno operator to the platform foundation

- **Status:** Accepted
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0556](0556-introduce-a-zuno-operator-with-foundation-infra-and-stack-crds.md) (introduce a zuno operator with Foundation, Infra and Stack CRDs)
- **Related:** [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md), [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0574](0574-deploy-unifai-through-argocd-from-a-pinned-olm-catalog.md)

## Context

ADR-0556 (`Proposed`, v0.9, contract only, no code) defines a `zuno` operator
with three cluster-scoped CRDs, each mirroring one playbook component list:

- `ZunoFoundation` (Day 0) covers `argocd` through `aap_config`.
- `ZunoInfra` (Day 1) ends with `aiagent_operator`.
- `ZunoStack` (Day 2) covers `namespaces, llm, models, rag, rag_ingestion,
  mcp, agents, mlops, trustyai_config, mlflow, lightspeed_config`, plus the
  check-only `supply_chain`.

The zuno operator applies and asserts ArgoCD Applications in order, and it
never reconciles another operator's objects (ADR-0556 clauses 1 and 3).

ADR-0561 replaces the agent layer with UnifAI, and ADR-0568 replaces
rag-service and rag-ingestion with UnifAI RAG. Three `ZunoStack` entries
(`rag`, `rag_ingestion`, `agents`) and one `ZunoInfra` entry
(`aiagent_operator`) therefore describe components that will not exist after
WP-156. Their replacement already has its own operator: `unifai-operator`
deploys a full UnifAI platform per namespace from one `UnifaiStack` and manages
its objects (`fork/unifai-operator/README.md`). `UnifaiStack` installs
UnifAI's private data services (MongoDB, Qdrant, RabbitMQ, Redis, Temporal).
It can also, with `identity.keycloak`, install an RHBK operator, a Keycloak and
a Crunchy `PostgresCluster` inside its namespace (same README, "Identity").
Keycloak and PostgreSQL are `ZunoFoundation` entries.

A second operator that also modelled agents, RAG or the UnifAI stack would
duplicate `unifai-operator`, and the two controllers would compete for the
same objects. That is the ownership fight ADR-0327's "Operational
considerations" was written to prevent.

## Decision

**The zuno operator owns the platform foundation: `ZunoFoundation`,
`ZunoInfra`, and the non-agent part of `ZunoStack`. The agent and RAG layer
is delegated to one `UnifaiStack` managed by `unifai-operator`.** The zuno
operator never creates, patches or deletes a `unifai.startx.fr` object.

**1. Component entries change as follows.**

- `ZunoInfra`: `aiagent_operator` is replaced by `unifai_operator`, which is
  the OLM-install half of ADR-0574's chart (pinned CatalogSource,
  OperatorGroup, Subscription with an explicit `source`).
- `ZunoStack`: `rag`, `rag_ingestion` and `agents` are removed, and `unifai`
  is added. `unifai` is the half of ADR-0574's chart that holds the
  `UnifaiStack`, the shared `UnifaiLLM`/`UnifaiProvider` objects and the
  `UnifaiAgentBundle` CRs (ADR-0564).
- The resulting `ZunoStack` list is `namespaces, llm, models, mcp, unifai,
  mlops, trustyai_config, mlflow, lightspeed_config`, plus the check-only
  `supply_chain`.

The Ansible lists that ADR-0556 mirrors change in the same commit, so the two
never describe different platforms.

**2. Delegation means asserting an Application and reading a status, never
rendering.** For the `unifai` entry, the zuno operator asserts that the ArgoCD
Application exists and is Synced. Its component condition is derived from
`UnifaiStack/unifai` `status.components[]` and the Ready conditions of the
`UnifaiAgentBundle`s, which it reads and never writes. The chart stays the only
source of the `UnifaiStack` spec (ADR-0556 clause 3: "charts remain the only
source of rendered config").

**3. Ordering is expressed in the existing entry order and gates.** `unifai`
comes after `llm` (the ai-gateway every UnifAI LLM points at, ADR-0560), after
`models` (remote embeddings on KServe, ADR-0568) and after `mcp`. Its
`UnifaiStack` uses `identity.external` against the Foundation's Keycloak
(ADR-0562), so it inherits ADR-0352 clause 10's vital gate unchanged.

**4. UnifAI never installs a Foundation service on a Zuno cluster.**
`identity.keycloak` is forbidden on Zuno clusters. The chart sets
`identity.external` only, and the `supply_chain` / `check` gate fails if a
`UnifaiStack` declares `identity.keycloak`. UnifAI's private data services
stay inside its namespace, owned by `unifai-operator`. They are not Foundation
or Infra entries and do not take ADR-0352's mode vocabulary. Their backup is
ADR-0568's Day-3 concern.

**5. `supply_chain` widens to UnifAI artifacts.** The check-only entry also
verifies the digests and signatures of the UnifAI images and of the OKF OCI
artifacts referenced by `UnifaiAgentBundle`s (ADR-0564, ADR-0574). It never
installs anything.

## Planned supersession

None. ADR-0556 is `Proposed` and contract-only, so the coordinator carries the
entry changes above into it as a dated, in-place amendment, as ADR-0352's
2026-09-10 amendment was carried. The retirement of the AIAgent operator is
recorded by ADR-0564's supersession of ADR-0308, ADR-0327 and ADR-0350.
ADR-0556 clause 3's interpretation of ADR-0327's negative boundary becomes
moot when ADR-0327 is superseded. The same reading applies to
`unifai-operator`: it installs UnifAI's own components, never the platform's.

## Consequences

The zuno operator's surface shrinks. It loses one Day 1 entry and three Day 2
entries, and it never has to model agents or RAG. That was its least stable
part, because it changes with every agent feature. The implementing work
package for ADR-0556 starts with `ZunoStack`, and that now means fewer
entries and no agent-specific reconciliation.

The cost is a two-operator chain for the agent layer: the zuno operator
asserts the Application, ArgoCD applies the chart, and `unifai-operator`
reconciles the stack. A failure in UnifAI therefore surfaces in the zuno
operator only as a derived condition. Diagnosis continues in
`kubectl get unifai -A`.

## Security considerations

The zuno operator's ClusterRole gains only `get/list/watch` on
`unifaistacks` and `unifaiagentbundles`, never write. It still holds no
provider credentials. `unifai-operator` is installed by OLM into
`openshift-operators` (fork `MEMORY.md`, "UnifAI operator") with its own
RBAC. Its privilege boundary is reviewed with ADR-0574, not widened by this
record. Forbidding `identity.keycloak` keeps a single identity provider per
cluster. A second Keycloak with its own admin user would be an unreviewed
identity silo.

## Operational considerations

Until the zuno operator is implemented, the boundary applies to the playbooks
directly: Day 1 installs `unifai_operator`, Day 2 installs `unifai`, and
neither touches the other's resources. On `demo333`, `unifai-operator`
currently tracks a catalog image tagged `latest` with `installPlanApproval:
Automatic` (fork `MEMORY.md`, `fork/unifai-operator/README.md`). ADR-0574
replaces that with a pinned catalog before this boundary is relied on.
