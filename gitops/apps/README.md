# GitOps applications

One subdirectory per platform component, each holding two ArgoCD
`Application` manifests: `<component>/application-d0.yaml` (operator
install and other cluster-scoped resources - `<app>-d0`) and
`<component>/application-d1.yaml` (CRD instances, pods, secrets - the live
service itself - `<app>-d1`). The matching Ansible role applies both
manifests directly (`-d0` first, then `-d1` once `-d0` is Synced+Healthy)
during `make day0|d0 install <component>` / `make day1|d1 install
<component>` (see `ansible/tasks/apply_gitops_app.yml`) - the only
mechanism `make day0|d0`/`day1|d1` uses to reconcile these Applications.

Most components have real content on only one side - a component with no
OLM operator (`vault`, `agent-runtime`, `ai-gateway`, `api`, `llm`, `mcp`,
`models`, `rag`) has an empty `-d0`, pointing at `gitops/charts/noop` (see
that chart's README). `mcp-sales-db` and `namespaces` have real content on
*both* sides: `mcp-sales-db`'s `-d0` (`gitops/charts/sql-schema`) is a
schema/fixtures prerequisite, not an operator. `namespaces`' `-d0`
(Namespace objects) and `-d1` (ResourceQuota/NetworkPolicy) also span the
*macro* Day 0/Day 1 split (`day0_install.yml` and `day1_install.yml`
respectively) - see `ansible/roles/namespaces/README.md`.

Every `Application.spec.project` here is `zuno`, not ArgoCD's built-in
`default` project - a dedicated `AppProject`
(`ansible/roles/argocd/kustomize/appproject/appproject.yaml`) applied by
the `argocd` role's `install.yml` once the `AppProject` CRD is
Established.

The root App-of-Apps (`gitops/root-app-of-apps.yaml`), which recurses over
this directory and manages every `application-d0.yaml`/`application-d1.yaml`
as a child Application, is no longer applied by Ansible - it is kept only
as a documented example of a pure-GitOps, Ansible-free bootstrap (see
`docs/platform/installation.md`). That path loses the `-d0`-before-`-d1`
ordering guarantee Ansible provides, since ArgoCD has no native dependency
between two separate `Application` objects; the `sync-wave` annotations
each `-d0`/`-d1` pair carries are cosmetic on that path.

Each `Application.spec.source` points either at an upstream Helm chart
(`repoURL` + `chart` + `targetRevision`) for well-known third-party
software, or at `gitops/charts/<component>` in this repository for
Zuno-authored manifests (Tekos FE/BFF, Agent Runtime, MCP Gateway, MCP tool
servers, namespace/quota scaffolding).

Not every component has an Application here. `argocd` is the sole
exception - it installs itself and creates the `AppProject` (`zuno`) every
`Application.spec.project` references, so it applies raw manifests
directly via `ansible/tasks/apply_kustomize.yml`. `admin_context` avoids
this since Day 0 now runs `argocd` first - see `admin-context` in the
table below. `vault`'s imperative unseal is a one-shot action, not a
standing component. `mlops` is out of scope for v0.

`sql_schema`'s and `rag`'s one-shot SQL `Job`s (schema/fixtures applies
against PostgreSQL) are covered here too, unlike `vault`'s unseal: each is
an ArgoCD `Sync` hook Job templated into the consuming chart
(`gitops/charts/sql-schema`'s `-d0` "prerequisites" Application for
`mcp-sales-db`; `gitops/charts/rag-service`'s own `-d1` Application for
`rag`), with `hook-delete-policy: BeforeHookCreation` (Jobs are immutable).
The static SQL/fixtures `ConfigMap` each Job mounts used to be Ansible-applied
for both (`ansible/roles/{sql_schema,rag}/kustomize/schema/`, plain
`configMapGenerator`s reading `data/{sxa,rag}/`), entirely outside GitOps -
`rag`'s is now rendered by the chart itself instead
(`gitops/charts/rag-service/templates/configmap-schema.yaml`, `.Files.Get`
on a copy of the same SQL under that chart's own `files/sql/`), so it's part
of the same ArgoCD-tracked flow as the Job that consumes it. `sql_schema`'s
ConfigMap (`zuno-sxa-schema`) is still the older Ansible-applied pattern.

`nfd`, `nvidia_gpu`, `openshift_ai`, `external_secrets`, `smtp` and
`observability` each have their own `-d0`/`-d1` Application pair backed by
one chart with `operator.enabled`/`<operand>.enabled`-style Helm value
toggles (see `gitops/charts/README` per-chart docs). The Subscription's
health is gated by a custom ArgoCD health check for
`operators.coreos.com/Subscription`
(`ansible/roles/argocd/tasks/apply_resource_health_checks.yml`) that the
including role's `install.yml` waits on before applying `-d1`.
`zuno-ai-run`'s `Namespace`, RHOAI dashboard label and GPU `ResourceQuota`
are owned by `gitops/charts/namespaces` instead.

`cert-manager` follows the same `-d0`/`-d1` shape: `-d0` installs the
operator (plus its own singleton `CertManager` config CR); `-d1` applies a
`ClusterIssuer` backed by a `pki/` secrets engine `ansible/roles/vault`
prepares (see that role's README). Consumed by `keycloak`'s Ingress and
`connectivity-link`'s Certificate.

**Vendored startx charts**: `machines`, `nfd`, `nvidia-gpu`, `openshift-ai`,
`cert-manager`, `keycloak`, `postgresql`, `connectivity-link`, `lws`,
`jobset`, `kueue`, `external-secrets`, `custom-metrics-autoscaler`, `kiali`,
`mesh-monitoring`, `observability` and `tempo` vendor a chart from the
[startx `helm-repository`](https://helm-repository.readthedocs.io) as a
Helm `dependencies:` entry, rather than hand-authoring their own
Namespace/OperatorGroup/Subscription. `helm dependency update` vendors the
chart's `.tgz` (gitignored, resolved at render time) and pins its version
in a committed `Chart.lock`. Only Zuno-specific content (the
`CertManager`/`ClusterIssuer` CRs, the Keycloak CR/RealmImport/
ExternalSecrets, the PostgresCluster/pgvector wiring, the discovered
`ClusterPolicy`/`DataScienceCluster` specs, and operand CRs like
`Kuadrant`/`KedaController`/`Kiali`/`OSSMConsole`/`MonitoringStack`/
`OpenTelemetryCollector`/`TempoMonolithic`/`OperatorConfig`/
`ClusterSecretStore`) stays as local templates.

`nfd`/`nvidia-gpu`/`openshift-ai`/`cert-manager` use that component's
matching `cluster-xxx` chart (`cluster-nfd`/`cluster-gpu`/`cluster-ods`/
`cluster-certmanager`), which bundles startx's own `project`+`operator`
dependencies; every other chart depends directly on the generic `operator`
chart (plus `project` when a dedicated Namespace is needed) - see each
chart's `Chart.yaml`/`values.yaml`. `connectivity-link`/`external-secrets`
subscribe into the shared `openshift-operators` namespace (`AllNamespaces`,
no `project`/`OperatorGroup`); `connectivity-link` still depends on
`project` for its Kuadrant operand namespace (`kuadrant-system`).
`jobset`/`kueue`/`lws`/`custom-metrics-autoscaler`/`kiali`/
`mesh-monitoring`/`observability`/`tempo` each depend on both `project`
and `operator` for their own dedicated operator namespace + `OperatorGroup`
(`openshift-{jobset,kueue,lws}-operator` for the first three): `kueue`'s
CSV only supports `AllNamespaces`, while `jobset`'s and `lws`'s CSVs only
support `OwnNamespace` (see the table below for each chart's `-d1`
content). `vault` was evaluated against `cluster-vault` and not migrated:
its `project` dependency isn't
needed (`zuno-data` already exists via `gitops/charts/namespaces`), and
adopting it would force an unrelated `hashicorp/vault` chart version jump
(0.28.1 → 1.21.2).

**`Namespace` resources on the `-d0` side**: every chart that declares its
own `Namespace` (the operator's dedicated namespace, or - for
`cert-manager`/`external-secrets` - a second namespace, or - for
`namespaces` - the whole set of platform/agent namespaces) renders it as
an ArgoCD `PreSync` hook (`argocd.argoproj.io/hook: PreSync`) rather than
a `sync-wave`'d resource, guaranteeing it exists before everything else in
the chart. No `hook-delete-policy` is set, so the `Namespace` persists
across re-syncs and is only removed when the Application itself is
deleted.

Independently, every `-d0` Application's `syncOptions.CreateNamespace` is
`true` whenever its `spec.destination.namespace` isn't already guaranteed
to exist some other way (`cert-manager`, `external-secrets`, `nfd`,
`nvidia-gpu`, `openshift-ai`, `observability`, and `namespaces` itself for
`zuno-ai-run`) - `false` everywhere else. Where both apply to the same
namespace (e.g. `cert-manager-operator`), they're deliberately redundant
safeguards.

`keycloak` and `postgresql` each have their own `-d0`/`-d1` pair the same
way as the six components above: their operand (`Keycloak`+
`KeycloakRealmImport`, `PostgresCluster`) is declarative here, and their
operator `Subscription` (+ `OperatorGroup` for `keycloak`) is too.

Directories present:

| Component | Source |
|---|---|
| `admin-context` | local chart, `gitops/charts/admin-context` (ADR-0314 - `-d0`: the four zuno `PriorityClass` objects, `priorityClasses.enabled`; `-d1`: the `startx` `HelmChartRepository`, `helmChartRepository.enabled`) - no operator, both halves are cluster-scoped |
| `vault` | local chart, `gitops/charts/vault` (wraps Helm chart `hashicorp/vault` as a dependency) - no operator, `-d0` is a no-op |
| `cert-manager` | local chart, `gitops/charts/cert-manager` (`-d0`: startx `cluster-certmanager` dependency for Namespace/OperatorGroup/Subscription + local `CertManager` config CR; `-d1`: Vault-backed `ClusterIssuer` - see the `cert_manager` role's README) |
| `keycloak` | local chart, `gitops/charts/keycloak` (`-d0`: startx `operator` dependency for the RHBK `Subscription`/`OperatorGroup` - not `cluster-sso`, see that chart's Chart.yaml; `-d1`: Keycloak CR/RealmImport/ExternalSecrets - ADR-0312, see the `keycloak` role's README) |
| `postgresql` | local chart, `gitops/charts/postgresql` (`-d0`: startx `operator` dependency for the PGO `Subscription` - not `cluster-crunchy`, see that chart's Chart.yaml; `-d1`: PostgresCluster/ExternalSecret/ConfigMap - ADR-0312, see the `postgresql` role's README) |
| `mariadb` | local chart, `gitops/charts/mariadb` (`-d0`: startx `operator` dependency for the open-source `mariadb-operator` `Subscription` into the shared `openshift-operators` namespace - no dedicated `OperatorGroup`, same Pattern B as `postgresql`, not the paid `mariadb-enterprise-operator` certified listing; `-d1`: `MariadbOperator` activation CR plus MariaDB/PhysicalBackup CRs and their ExternalSecrets, see the `mariadb` role's README) |
| `models` | local chart, `gitops/charts/models` (KServe ServingRuntime + InferenceService) - no operator, `-d0` is a no-op |
| `mcp` | local chart, `gitops/charts/mcp-gateway` - no operator, `-d0` is a no-op |
| `rag` | local chart, `gitops/charts/rag-service` - no operator, `-d0` is a no-op |
| `ai-gateway` | local chart, `gitops/charts/ai-gateway` (applied by the `llm` role, see its README; ADR-0009) - no operator, `-d0` is a no-op |
| `agent-runtime` | local chart, `gitops/charts/agent-runtime` (applied by the `llm` role, see its README) - no operator, `-d0` is a no-op |
| `namespaces` | local chart, `gitops/charts/namespaces` (`-d0`: Namespace objects, `namespace.enabled`; `-d1`: ResourceQuota/NetworkPolicy scaffolding, `policy.enabled` - spans the macro Day 0/Day 1 split, not just this component's own internal ordering) |
| `api` | local chart, `gitops/charts/tekos` - no operator, `-d0` is a no-op |
| `llm` | native Kustomize app, `platform/ai-gateway/` (provider routing ConfigMap + provider `ExternalSecret`s) - no operator, `-d0` is a no-op |
| `mcp-sales-db` | local chart, `gitops/charts/mcp-sales-db` (applied by the `sql_schema` role, after its schema/fixtures Job) - no operator, `-d0` is a no-op |
| `machines` | local chart, `gitops/charts/machines` (ADR-0351 - `-d0`: startx `cluster-machine` dependency for the GPU MachineSets/MachineAutoscaler/ClusterAutoscaler, all cluster-scoped, no operator; `-d1` is a no-op - see that chart's README for the scale-from-zero and AZ-failover design) |
| `nfd` | local chart, `gitops/charts/nfd` (ADR-0312 - `-d0`: startx `cluster-nfd` dependency, entirely - Namespace/OperatorGroup/Subscription; `-d1`: `cluster-nfd`'s own NodeFeatureDiscovery CR) |
| `nvidia-gpu` | local chart, `gitops/charts/nvidia-gpu` (ADR-0312 - `-d0`: startx `cluster-gpu` dependency for Namespace/OperatorGroup/Subscription; `-d1`: `cluster-gpu`'s own ClusterPolicy CR, spec injected once discovered - see that chart's README) |
| `openshift-ai` | local chart, `gitops/charts/openshift-ai` (ADR-0312 - `-d0`: startx `cluster-ods` dependency for Namespace/OperatorGroup/Subscription; `-d1`: `cluster-ods`'s own DataScienceCluster CR, spec overridden in full - RawDeployment, not startx's Serverless-dependent default) |
| `external-secrets` | local chart, `gitops/charts/external-secrets` (ADR-0312 - `-d0`: startx `operator` dependency for the `Subscription` into `openshift-operators` (`AllNamespaces`, no `OperatorGroup`), plus local `OperatorConfig`; `-d1`: ClusterSecretStore/cluster-domain ExternalSecret, rendered only once the discovered Vault Service name is supplied - see the `external_secrets` role's README) |
| `smtp` | local chart, `gitops/charts/smtp` (`-d0`: zuno-ai-run Namespace; `-d1`: technical mail identity ExternalSecret) - no operator |
| `observability` | local chart, `gitops/charts/observability` (`-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-opentelemetry-operator` Namespace/OperatorGroup/Subscription; `-d1`: shared OTLP Collector, exporting to both `debug` and `tempo`'s `otlp/tempo`) |
| `service-mesh` | local chart, `gitops/charts/service-mesh` (`-d0`: startx `cluster-istio` dependency, `operatorIstio.enabled`, installs the servicemeshoperator3/Sail Operator; `-d1`: Vault-backed mesh CA (`clusterIssuer`/`istioCsr`), `istiocni` and the `istio` control plane itself, in zuno-mesh) |
| `connectivity-link` | local chart, `gitops/charts/connectivity-link` (ADR-0317 - `-d0`: startx `operator` dependency for the `Subscription` into `openshift-operators` (`AllNamespaces` - the operator's CSV doesn't support `OwnNamespace`, confirmed against a real cluster), no `OperatorGroup`; `-d1`: startx `project` dependency for the dedicated `kuadrant-system` Namespace + minimal empty `Kuadrant` operand CR) |
| `lws` | local chart, `gitops/charts/lws` (ADR-0317 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-lws-operator` Namespace/OperatorGroup (`OwnNamespace` - the operator's CSV doesn't support `AllNamespaces`, confirmed against a real cluster after subscribing via the shared `openshift-operators` namespace's `AllNamespaces` OperatorGroup left the CSV Failed)/Subscription; `-d1` is a no-op, no singleton operand CR exists for LeaderWorkerSet) |
| `custom-metrics-autoscaler` | local chart, `gitops/charts/custom-metrics-autoscaler` (ADR-0318 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-keda` Namespace/OperatorGroup/Subscription (`OwnNamespace`, per Red Hat's documented install procedure); `-d1`: minimal `KedaController` operand CR) |
| `jobset` | local chart, `gitops/charts/jobset` (ADR-0318 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-jobset-operator` Namespace/OperatorGroup (`OwnNamespace` - the operator's CSV doesn't support `AllNamespaces`, confirmed against a real cluster after subscribing via the shared `openshift-operators` namespace's `AllNamespaces` OperatorGroup left the CSV Failed)/Subscription; `-d1`: minimal, cluster-scoped `JobSetOperator` operand CR, `managementState: Managed`) |
| `kueue` | local chart, `gitops/charts/kueue` (ADR-0321 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-kueue-operator` Namespace/OperatorGroup (`AllNamespaces` - the operator's CSV doesn't support any other install mode, confirmed against a real cluster); `-d1`: singleton `Kueue` operand CR plus default `ResourceFlavor`/`ClusterQueue`/`LocalQueue` - installed ahead of `openshift-ai`, whose `DataScienceCluster` sets `kueue.managementState: Unmanaged` to defer to this operator) |
| `tempo` | local chart, `gitops/charts/tempo` (ADR-0312 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-tempo-operator` Namespace/OperatorGroup/Subscription; `-d1`: demo-scale `TempoMonolithic` in zuno-monitoring, storing traces exported by `observability`'s Collector) |
| `mesh-monitoring` | local chart, `gitops/charts/mesh-monitoring` (ADR-0312 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-cluster-observability-operator` Namespace/OperatorGroup/Subscription; `-d1`: `MonitoringStack` + ServiceMonitor/PodMonitor scraping istiod and mesh Envoy sidecars in zuno-mesh - no OpenShift User Workload Monitoring exists in this repo to use instead) |
| `kiali` | local chart, `gitops/charts/kiali` (ADR-0312 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-kiali-operator` Namespace/OperatorGroup/Subscription; `-d1`: `Kiali` CR in zuno-mesh, wired to `mesh-monitoring`'s Prometheus and `tempo`'s Tempo - the operator owns its own auto-created Route, not tracked as a separate chart resource) |

`keycloak`, `api` and `vault`'s `Application.spec.source.helm.values`
reference `clusterBaseDomain: apps.mycluster.example.com` - a token, not a
literal domain. `ansible/tasks/apply_gitops_app.yml` substitutes it with
the real cluster's apps wildcard domain, auto-discovered from
`Ingress.config.openshift.io/cluster` and persisted to Vault at
`zuno/platform/cluster-domain` (see
`ansible/tasks/resolve_cluster_base_domain.yml` and
`ansible/roles/vault/tasks/install.yml`) - no manual edit needed before a
real deployment. Because `gitops_app_extra_helm_values` replaces
`spec.source.helm.values` wholesale rather than merging with it, any role
that both needs this substitution *and* sets extra Helm values (currently
`keycloak`'s `-d1` apply) must re-supply `clusterBaseDomain` itself from
the already-resolved `cluster_base_domain` fact - see that role's
`tasks/install.yml`. `ansible/roles/external_secrets` also exposes that
Vault value as a `zuno-cluster-domain` Secret in `zuno-ai-run` for any
service that wants it as a live runtime value rather than a
Helm-render-time one (not yet consumed by any service).
