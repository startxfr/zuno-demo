# ADR-0548: Remove the unused zuno-ai-platform reserved namespace

- **Status:** Implemented
- **Target:** v0.8
- **Date:** 2026-09-04
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md), [ADR-0333](0333-separate-product-managed-ai-infrastructure-from-zuno-build-run-and-shared-platform-namespaces.md)
- **Relationship to prior ADRs:** Retires only the `zuno-ai-platform` reserved shared-services namespace introduced by [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) and reaffirmed by [ADR-0333](0333-separate-product-managed-ai-infrastructure-from-zuno-build-run-and-shared-platform-namespaces.md). It does not reopen [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md)'s revert of RHOAI to its default namespaces, ADR-0333's product-managed-namespace rules (`redhat-ods-*`, `openshift-ingress*`, Gateway API, Connectivity Link/Kuadrant), or the `zuno-ai-build`/`zuno-ai-run`/`zuno-mlops` workload-plane split, all of which remain in effect unchanged.

## Context

ADR-0328 introduced `zuno-ai-platform` as the shared OpenShift AI control-plane namespace: the intended home for RHOAI's `applicationsNamespace`, the Model Registry, AI Gateway, OGX and every other component shared between the build and run lifecycles. ADR-0331 reverted the RHOAI operand placement back to `redhat-ods-applications`/`rhoai-model-registries` after `trainer`/`ray`/`dashboard`/`mlflowoperator` all broke under a custom `applicationsNamespace` on RHOAI 3.5 EA2, leaving `zuno-ai-platform` empty. ADR-0333 reaffirmed the namespace as "reserved" (a SHOULD, not a MUST) for future Zuno-managed BUILD/RUN shared services, kept it in the namespace decision algorithm, and made its existence a Day 0 acceptance-criteria and precheck requirement (`ansible/roles/namespaces/tasks/precheck.yml`).

More than two weeks after ADR-0333 (2026-08-22 to 2026-09-04), the reservation has never been used. Every shared runtime service that actually exists today — `mcp-gateway`, `mcp-sales-db`, `ai-gateway`, `agent-runtime`, `tekos`, the RAG service — was deployed directly into `zuno-ai-run` instead, and the one component ADR-0333 explicitly designed the namespace for, the Model Registry, ended up in `rhoai-model-registries` (a documented exception, not `zuno-ai-platform`). The namespace still carries full governance (`NetworkPolicy`, `ResourceQuota`, `LimitRange`, mesh sidecar injection) and is checked for existence on every `make d0 check` run, but hosts no `CustomResource`, `Deployment`, `Operator`, `Subscription`/`OperatorGroup`, webhook or ArgoCD `Application`. A 2026-09-04 review (triggered by a direct user question about the namespace's purpose) confirmed:

- no live or GitOps-managed object is scoped to `zuno-ai-platform` beyond the `Namespace` object itself and its generic governance templates;
- no `Subscription`/`OperatorGroup`, webhook, RBAC binding or CRD is bound to this namespace specifically — the one attempt to host an Operator's operands there (RHOAI) already failed and was reverted by ADR-0331, which is itself evidence the namespace has never successfully anchored a real workload;
- no application code (Python/Go/Ansible/shell) references the namespace name; only GitOps manifests, the Ansible Day 0 precheck, and documentation do.

Keeping an empty, governance-bearing namespace whose only proven behavior is "an Operator broke when it was placed here" adds architectural confusion for no operational benefit, and prompted this review in the first place.

## Decision

Remove `zuno-ai-platform` entirely: delete the `Namespace` object (and its `ResourceQuota`/`LimitRange`/`NetworkPolicy` overlay) from the GitOps-managed chart, and retire the "Zuno-managed shared BUILD/RUN" branch of ADR-0333's namespace decision algorithm and Day 0/Day 1 acceptance criteria.

Going forward, a Zuno-managed component shared between build and run that does not have an Operator-imposed namespace resolves directly to `zuno-ai-run` — matching what every real shared service already does today, not a reserved shared-platform namespace that has never been used. If a genuine need for a dedicated shared-services namespace re-emerges, it requires a new ADR evaluating the concrete component driving it, not a revival of this one.

### Concrete changes

- `gitops/charts/namespaces/values.yaml` — remove the `zuno-ai-platform` entry from `platformNamespaces`, and its corresponding entry from the mesh-control-plane egress allowlist (`templates/networkpolicy-mesh-egress.yaml`'s allowed-namespaces list).
- `ansible/roles/namespaces/tasks/precheck.yml` — remove `zuno-ai-platform` from ADR-0333's `_namespace_topology_required` list; the Day 0 topology check no longer expects this namespace to exist.
- `ansible/roles/namespaces/README.md`, `gitops/charts/namespaces/README.md` — drop it from the documented namespace list.
- `docs/architecture/physical-architecture.md`, `docs/security/secnumcloud-controls.md` — drop it from the namespace/mesh-injection/NetworkPolicy-baseline lists.
- ADR-0328's and ADR-0333's `Status` lines are updated to `Superseded in part by ADR-0548` for the `zuno-ai-platform` clauses specifically; every other clause in both ADRs (the build/run split, product-managed-namespace rules, ingress/Gateway API/Connectivity Link placement) is unaffected and remains in force.
- `docs/adr/0330`, `docs/adr/0331`, `platform/openshift-ai/README.md` and `gitops/charts/openshift-ai/values.yaml` are left untouched: their mentions of `zuno-ai-platform` are historical record of a decision already reverted (ADR-0331), and rewriting them would misrepresent that history.

ArgoCD is the removal mechanism: both `zuno-namespaces-d0` and `zuno-namespaces-d1` (`gitops/apps/namespaces/application-d0.yaml`/`application-d1.yaml`) run `syncPolicy.automated.prune: true`, so once the chart change merges to `main`, ArgoCD deletes the live `Namespace` object (and its Day 1 `ResourceQuota`/`NetworkPolicy`/`LimitRange`) itself on its next sync — no manual `oc delete namespace` is required or should be used instead of this path.

## Consequences

### Positive

- Removes an empty namespace that has never anchored a real workload, plus its Day 0 precheck requirement and governance overhead.
- Simplifies ADR-0333's decision algorithm to match what every real shared service already does (resolve to `zuno-ai-run`).
- Removes one recurring source of confusion (this ADR exists because a direct question about the namespace's purpose turned up nothing using it).

### Negative

- If a future Zuno-managed shared BUILD/RUN service needs namespace isolation from `zuno-ai-run`, that requires a new ADR and namespace introduction from scratch, rather than reusing an already-reserved one.
- ADR-0328 and ADR-0333 now carry two independent partial-supersession qualifiers each on unrelated clauses (`applicationsNamespace` vs. the reserved namespace itself), which readers must parse carefully.

## Acceptance criteria

- [x] `gitops/charts/namespaces/values.yaml` no longer lists `zuno-ai-platform` in `platformNamespaces` or the mesh-egress allowlist.
- [x] `ansible/roles/namespaces/tasks/precheck.yml`'s required namespace topology no longer includes `zuno-ai-platform`.
- [x] The live cluster's `zuno-ai-platform` `Namespace` object is gone: live-verified 2026-09-04 after commit `b2d02cff` merged to `main` - `zuno-namespaces-d0`/`zuno-namespaces-d1` (ArgoCD) picked it up on a hard refresh, transitioned the namespace to `Terminating`, and it was fully deleted within ~2 minutes. Pruned by ArgoCD (`syncPolicy.automated.prune: true`), no manual `oc delete namespace` used. Both Applications are `Synced`/`Healthy` afterward; no other namespace or resource was affected.
- [x] `platform/docs/check_docs.py` passes: ADR-0328 and ADR-0333's `Status` lines and their `docs/adr/README.md` index rows agree, and both name ADR-0548.

## Related ADRs

- [ADR-0328](0328-separate-the-openshift-ai-control-plane-from-ai-build-and-run-workload-namespaces.md) — introduced the namespace this ADR removes
- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md) — reverted the one workload placement ever attempted in it
- [ADR-0333](0333-separate-product-managed-ai-infrastructure-from-zuno-build-run-and-shared-platform-namespaces.md) — reaffirmed it as reserved; that reservation is what this ADR retires
