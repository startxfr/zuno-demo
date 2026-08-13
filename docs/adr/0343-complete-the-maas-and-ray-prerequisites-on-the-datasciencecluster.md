# ADR-0343: Complete the MaaS and Ray prerequisites on the DataScienceCluster

- **Status:** Implemented
- **Target:** v1
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

After ADR-0331 reverted RHOAI to its default `redhat-ods-applications` namespace, the `zuno-dsc` DataScienceCluster still reported `Ready=False` on the test cluster, with four distinct root causes found by live investigation (2026-08-13):

1. **Authorino TLS off** (`MaaSPrerequisitesAvailable=False`): the fix already existed in git (`gitops/charts/connectivity-link/templates/authorino.yaml` + `certificate.yaml`, flag flipped in `gitops/apps/connectivity-link/application-d1.yaml`), but the live ArgoCD Application CR predated it. Application manifests are applied by Ansible, not synced from git (ADR-0311 removed the root App-of-Apps), so an Application-level helm-values change is invisible to the cluster until the manifest is re-applied - the charts it points at auto-sync, the Application itself does not.
2. **`maas-db-config` Secret missing** in `redhat-ods-applications`: `maas-api` CrashLoops on startup without a `DB_CONNECTION_URL`.
3. **User Workload Monitoring not enabled**: no `cluster-monitoring-config` ConfigMap in `openshift-monitoring`; MaaS showback/FinOps views depend on it and `ModelsAsServiceReady` reports it as an unmet prerequisite.
4. **`RayReady=False` at 0/1**: `redhat-ods-applications` is namespace-injected into the mesh (`istio-injection: enabled`, gitops/charts/namespaces), and the injected istio init containers (proxy uid 1001419999, the namespace range's last uid) make `kuberay-operator` pods unvalidatable by every SCC on the cluster - RHOAI's own `run-as-ray-user` SCC pins uid 1000. The `kserve-localmodelnode-agent` DaemonSet fails identically against `openshift-ai-localmodel-scc`.

## Decision

Treat all four as MaaS/Ray platform prerequisites and close them in the existing GitOps structure, without adding new components:

- **Authorino TLS**: no new code - re-apply `gitops/apps/connectivity-link/application-d1.yaml` so the live Application carries the `authorinoTls` values. Operationally: any change to an Application manifest's inline helm values requires an explicit re-apply (Ansible flow or `oc apply`), and other live Application CRs should be diffed against `gitops/apps/**` when drift is suspected.
- **MaaS database**: a fourth dedicated database/role (`maas`) on the shared `zuno-postgresql` PGO cluster, exactly the ADR-0315 keycloak pattern - Vault-seeded credential (`zuno/maas/postgresql-app`, letters/digits-only so it can be interpolated un-encoded into a URI), "bring your own password" ExternalSecret in `zuno-data` (`gitops/charts/postgresql/templates/externalsecret-maas.yaml`), and a consumer-side ExternalSecret rendering `maas-db-config` with `DB_CONNECTION_URL` in `redhat-ods-applications` (`gitops/charts/openshift-ai/templates/externalsecret-maas-db.yaml`, targeting `zuno-postgresql-primary` rather than pgbouncer to avoid transaction-pooling/prepared-statement pitfalls). `redhat-ods-applications` is added to `zuno-data`'s `allowedFromNamespaces`.
- **User Workload Monitoring**: `gitops/charts/openshift-ai/templates/cluster-monitoring-config.yaml` renders the `cluster-monitoring-config` ConfigMap (single key, `enableUserWorkload: true`), opted in from the d0 Application as a cluster-level prerequisite.
- **Ray/localmodel SCC conflict**: exclude the two RHOAI-managed workloads from sidecar injection at the injector (`sidecarInjectorWebhook.neverInjectSelector` on the Istio CR, `gitops/charts/service-mesh/templates/istio.yaml`) rather than de-meshing the namespace or hand-crafting an SCC - RHOAI owns the pod templates, so per-pod `inject=false` is not available, and `maas-api` legitimately needs its sidecar.

## Consequences

`zuno-dsc` can reach `Ready=True` with `modelsasservice` and `ray` reconciled. The maas database inherits `zuno-postgresql`'s HA/backup lifecycle. Two RHOAI workloads in an otherwise mesh-injected namespace run outside the mesh; any future mTLS-required path to them must revisit the exclusion. The `cluster-monitoring-config` ConfigMap is now ArgoCD-owned - future cluster-monitoring tuning must be merged into that template, not applied by hand.

## Security considerations

The maas credential is generated and lives only in Vault; both ExternalSecrets resolve the same path, so rotation is a single Vault write followed by ESO refresh. The de-meshed kuberay/localmodelnode pods talk only to the API server (operator pattern), so losing sidecar mTLS does not expose an application data path. NetworkPolicy widening is limited to `redhat-ods-applications -> zuno-data`.

## Operational considerations

The `maas-api-key-cleanup` CronJob's istio-proxy init fails its startup probe every run - deliberately NOT excluded from injection (its pods need the maas database in mTLS-enforced `zuno-data`); revisit via `global.proxy.startupProbe` tuning after this lands. The Kuadrant operator co-owns the Authorino CR with ArgoCD; the chart intentionally asserts only `spec.listener.tls`.

## Acceptance criteria

- `oc get datasciencecluster zuno-dsc` shows `Ready`, `MaaSPrerequisitesAvailable`, `ModelsAsServiceReady` and `RayReady` all `True`.
- `maas-api` runs 2/2 with a working database connection; `kuberay-operator` 1/1 with no injected sidecar.
- `authorino` in `kuadrant-system` has `spec.listener.tls.enabled=true` backed by the cert-manager `authorino-server-tls` Certificate (vault-issuer).
- UWM stack pods run in `openshift-user-workload-monitoring`.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md)
- [ADR-0315](0315-dedicated-keycloak-postgresql-database.md)
- [ADR-0317](0317-install-connectivity-link-and-leaderworkerset-operators.md)
- [ADR-0331](0331-revert-openshift-ai-to-the-default-applications-namespace.md)
