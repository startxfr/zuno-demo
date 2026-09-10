# ADR-0556: Introduce a zuno operator with Foundation, Infra and Stack CRDs

- **Status:** Proposed
- **Target:** v0.9
- **Date:** 2026-09-10
- **Decision owners:** Zuno Demo architecture team

## Context

The platform's lifecycle is driven by three Ansible playbook families —
Day 0 (13 components, `ansible/playbooks/day0_*.yml`), Day 1 (23
components) and Day 2 (11 components, plus the check-only
`supply_chain` gate) — sequenced by ADR-0056 / ADR-0060 / ADR-0421,
dispatched through `make` (ADR-0030), and re-runnable as AAP job
templates (ADR-0418). What a cluster *should* run is therefore encoded
in playbook variable lists and Makefile variables, not in any object
the cluster itself holds; drift between the two has already happened
(`image_mirrors`), and reconciliation is something an operator runs,
not something that runs continuously.

The repo already owns one operator: the AIAgent operator
(`operator/aiagent-operator/`, group `zuno.zuno.ai`, `v1alpha1`),
built contract-first — ADR-0327 fixed its CRD and reconciliation
boundary before ADR-0308 implemented it, and that boundary is
deliberately narrow: the AIAgent operator must **not** install
OpenShift AI, Keycloak, PostgreSQL, Vault or other shared services.
Nothing today may install them declaratively; only the playbooks do.

ADR-0352 (amended 2026-09-10) gives every component a mode vocabulary
— `internal | external` with a typed external payload — and ADR-0547
makes every cluster-specific value an Ansible parameter. Together they
define exactly the information a per-cluster declarative object would
carry. This ADR is the long-term destination for that vocabulary: a
cluster describes its own platform in CRs, and an operator reconciles
it.

## Decision

This is a **contract ADR**, following the ADR-0327 → ADR-0308
precedent: it fixes the CRDs, the boundary and the migration posture;
implementation lands under a later ADR/work-package pair.

### 1. One operator, beside the AIAgent operator

A new `zuno` operator lives in its own module under `operator/` (e.g.
`operator/zuno-operator/`), sharing nothing with
`operator/aiagent-operator/` but the API group `zuno.zuno.ai` and the
repo's operator conventions — kubebuilder layout, a `CONTRACT.md`
restating this ADR, and a `validate_contract.py` that machine-enforces
it (the pattern `operator/aiagent-operator/` set). Functionally it
sits *above* the AIAgent operator — it may install what the AIAgent
operator is forbidden to touch — but its code sits beside it, and
neither reconciles the other's objects.

### 2. Three cluster-scoped CRDs, one instance of each per cluster

All in `zuno.zuno.ai/v1alpha1`, each spec mirroring one playbook
component list — same names, same order, so the playbooks and the CRDs
cannot describe two different platforms:

- **`ZunoFoundation`** — Day 0. One spec entry per component:
  `argocd, admin_context, namespaces, image_mirrors,
  openshift_rbac_groups, vault, external_secrets, cert_manager,
  machines, postgresql, keycloak, aap, aap_config`. Entries for
  ADR-0352 Tier-A components carry `mode: internal | external` plus
  the external payload, **reusing ADR-0352's clause-2 vocabulary
  verbatim** — this ADR introduces no second mode schema. Tier-C
  entries carry configuration only.
- **`ZunoInfra`** — Day 1. One spec entry per component:
  `smtp, nfd, nvidia_gpu, custom_metrics_autoscaler, redis,
  observability, service_mesh, mesh_monitoring, kiali, grafana,
  perses, mariadb, tempo, openshift_oauth, connectivity_link, lws,
  jobset, kueue, openshift_ai, lightspeed, rhtas, rhtas_config,
  aiagent_operator`. Per ADR-0352, only `redis` and `mariadb` accept
  `mode: external` (and `smtp` stays the degenerate always-external
  case).
- **`ZunoStack`** — Day 2. One spec entry per component:
  `namespaces, llm, models, rag, rag_ingestion, mcp, agents, mlops,
  trustyai_config, mlflow, lightspeed_config` — plus `supply_chain`,
  which is **check-only by design** (ADR-0420/WP-070: a pure
  signature-verification gate, no install/build of its own — since
  2026-09-10 the Makefile expresses this as
  `DAY2_CHECK_ONLY_COMPONENTS`); its spec entry is likewise a
  verification-only entry the operator asserts but never installs. No
  mode key: Day 2 is the platform's own workload plane.

Secrets never appear in a CR: external credentials keep flowing
`confidential.yml` → Vault KV → ExternalSecrets (ADR-0352 clause 8);
the CRs reference, never contain — the same rule ADR-0327 set for
AIAgent.

### 3. Reconciliation boundary

- The zuno operator owns the **orchestration** the playbooks perform
  today: applying ArgoCD Applications in component order, running the
  clause-4 assert-external logic, enforcing ADR-0352's clause-10
  vital gate (a `ZunoInfra` does not progress until its cluster's
  `ZunoFoundation` reports the seven vital components functional) and
  surfacing what `make dN check` reports today as `status.conditions`
  — one condition per component, plus a roll-up.
- It does **not** replace ArgoCD: charts remain the only source of
  rendered config, Applications remain the delivery vehicle
  (ADR-0311/0312), and the operator applies/asserts Applications the
  way Ansible does now — it becomes the thing that runs the loop, not
  a second renderer.
- It does not touch AIAgent CRs or their children; conversely
  ADR-0327's negative boundary ("the operator must not install
  Keycloak, PostgreSQL, Vault…") is **per-operator, not platform-wide**
  — it continues to bind the AIAgent operator exactly as written, and
  the zuno operator is precisely the component that holds the
  installing role. No supersession of ADR-0327 is needed; this clause
  is the recorded interpretation.
- Destructive verbs (uninstall, restore) stay human-triggered: the
  operator reconciles toward presence and reports drift; it never
  deletes a component because a spec entry disappeared, mirroring the
  ADR-0418 posture that destructive AAP verbs sit behind explicit
  approval.

### 4. Migration is progressive, playbooks stay primary

The playbooks and `make` verbs remain the operator-facing interface
(as ADR-0418 kept them alongside AAP). Sequencing: (1) CRDs land as
**record-only** — the roles write status into them, nothing reconciles;
(2) `check` verbs read from CR status; (3) reconciliation is enabled
per-day, `ZunoStack` first (smallest blast radius, no vital
components), `ZunoFoundation` last. Each step is its own work package
with a live inertia proof, per the ADR-0547 clause-4 discipline. A
flag day where playbooks stop working is explicitly not part of this
contract.

## Consequences

- The per-cluster platform definition becomes a cluster-resident,
  `oc get`-able object instead of the cross product of playbook lists,
  Makefile variables and `confidential.yml` — and the three lists gain
  a single point of truth the CRD schema enforces.
- A second operator means a second CRD lifecycle, controller image and
  build/sign chain (`make d1 build` + ADR-0535 signing), accepted as
  the cost of continuous reconciliation.
- ADR-0352's mode vocabulary becomes an API surface: future changes to
  its clause-2 schema must stay CRD-compatible or version the API.

## Security considerations

The zuno operator is by construction the most privileged controller on
the cluster — it installs operators, creates namespaces and applies
cluster-scoped objects. Its ServiceAccount must be a purpose-built
ClusterRole enumerating exactly the playbooks' surface (the
`zuno-aap-installer` role from ADR-0418 is the precedent and likely
starting point), never cluster-admin. It reads secrets only through
the ExternalSecrets seam and holds no provider credentials of its own.
CR write access is the new privilege boundary: whoever can edit a
`ZunoFoundation` can re-point Vault or Keycloak, so the CRs live
behind admin-only RBAC and, like every other desired-state object,
under GitOps review.

## Acceptance criteria

(This ADR delivers the contract only; implementation acceptance lives
with its future work packages.)

- This ADR exists with the three CRD specs mirroring the current
  playbook component lists and the boundary clauses above.
- The `## v0.9` index table in `docs/adr/README.md` has the ADR-0556
  row and its status matches the body.
- No implementation surface has changed: no CRD, no `operator/zuno-*`
  code, no playbook change lands under this ADR.
- The implementing ADR/WP, when authored, starts from this contract
  and the `CONTRACT.md` + validator pattern.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0030](0030-use-a-command-dispatch-makefile-interface.md)
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md)
- [ADR-0060](0060-restructure-day-0-day-1-day-2-day-3-deployment-sequencing.md)
- [ADR-0308](0308-expand-agent-lifecycle-management-through-the-aiagent-operator.md)
- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md)
- [ADR-0327](0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
- [ADR-0350](0350-provide-an-aiagent-kubernetes-crd-and-operator.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- [ADR-0418](0418-execute-day-0-and-day-1-operations-as-aap-job-templates.md)
- [ADR-0421](0421-reshape-day-0-day-1-boundaries-around-always-on-infra.md)
- [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md)
- [ADR-0557](0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md)
