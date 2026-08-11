# GitOps applications

One subdirectory per platform component, each holding two ArgoCD
`Application` manifests: `<component>/application-d0.yaml` (operator
install and other cluster-scoped resources - `<app>-d0`) and
`<component>/application-d1.yaml` (CRD instances, pods, secrets - the live
service itself - `<app>-d1`). The matching Ansible role applies both
manifests directly (`-d0` first, then `-d1` once `-d0` is Synced+Healthy)
during `make day0|d0 install <component>` / `make day1|d1 install
<component>` (ADR-0056; see `ansible/tasks/apply_gitops_app.yml`) - this is
the only mechanism `make day0|d0`/`day1|d1` uses to reconcile these
Applications, so a single component can always be installed without a full
sync.

Most components have real content on only one side - a component with no
OLM operator (`vault`, `agent-runtime`, `ai-gateway`, `api`, `llm`, `mcp`,
`models`, `rag`) has an empty `-d0`. The empty side points at
`gitops/charts/noop` (see that chart's README) rather than being omitted,
so the `-d0`/`-d1` naming convention is uniform and visible across every
component directory. `mcp-sales-db` and `namespaces` have real content on
*both* sides: `mcp-sales-db`'s `-d0` (`gitops/charts/sql-schema`) is a
schema/fixtures prerequisite, not an operator, but the same "prerequisites
before the live service" ordering the `-d0`/`-d1` split provides for every
other component fits it too (ADR-0313). `namespaces`' `-d0` (Namespace
objects) and `-d1` (ResourceQuota/NetworkPolicy) are the one component pair
that also spans the *macro* Day 0/Day 1 split (`day0_install.yml` and
`day1_install.yml` respectively, not just Day 0's own internal ordering) -
see `ansible/roles/namespaces/README.md` for why.

Every `Application.spec.project` here is `zuno`, not ArgoCD's built-in
`default` project - a dedicated `AppProject` (`ansible/roles/argocd/
kustomize/appproject/appproject.yaml`) applied by the `argocd` role's own
`install.yml`, once it has installed the operator that owns the
`AppProject` CRD and waited for that CRD to be Established.
Keeping every zuno-* Application on a named, scoped project - rather than
whatever else on the cluster shares `default` - makes its RBAC/permissions
an explicit, auditable grant instead of an implicit one.

The root App-of-Apps (`gitops/root-app-of-apps.yaml`), which recurses over
this directory and manages every `application-d0.yaml`/`application-d1.yaml`
it finds as a child Application, is no longer applied by Ansible (ADR-0311,
superseding the "Bootstrap architecture" addendum in
docs/adr/0022-use-gitops-managed-declarative-agent-tasks-and-policies.md).
It is kept in the repository only as a documented example of a
pure-GitOps, Ansible-free bootstrap - see `docs/platform/installation.md`.
That path loses the `-d0`-before-`-d1` ordering guarantee Ansible provides
by applying the two Applications sequentially: ArgoCD has no native
dependency between two separate `Application` objects, only `sync-wave`
ordering *within* one Application's own resource graph. The `sync-wave`
annotations each `-d0`/`-d1` pair still carries are therefore cosmetic
documentation of intent on that path, consistent with ADR-0311's existing
"non-operational" framing of the root App-of-Apps.

Each `Application.spec.source` points either at an upstream Helm chart
(`repoURL` + `chart` + `targetRevision`) for well-known third-party software
(Keycloak Operator, Crunchy Postgres Operator, vLLM/KServe runtimes, External Secrets
Operator config), or at `gitops/charts/<component>` in this repository for
Zuno-authored manifests (Tekos FE/BFF, Agent Runtime, MCP Gateway, MCP tool
servers, namespace/quota scaffolding).

Not every component has an Application here. `argocd` is the sole remaining
exception - it installs itself and creates the `AppProject` (`zuno`) every
`Application.spec.project` here references, a bootstrap chicken-and-egg no
`Application` can resolve, so it still applies raw manifests directly via
`ansible/tasks/apply_kustomize.yml` (ADR-0310). `admin_context` used to be
in this bucket too, for the same reason, but the Day 0 sequence now runs
`argocd` before it, so the `AppProject` is always already in place by the
time `admin_context` registers its own Applications - see `admin-context`
in the table below and ADR-0314. `vault`'s imperative unseal is likewise a
one-shot/imperative action rather than a standing installed component, and
stays outside this directory for the same reason - it calls Vault's own API
and captures generated secret material at runtime, which no combination of
ArgoCD/Helm can express. `mlops` is out of scope for v0 (ADR-0301/0302 are
v3).

`sql_schema`'s and `rag`'s one-shot SQL `Job`s (schema/fixtures applies
against PostgreSQL) *are* covered here as of ADR-0313, unlike `vault`'s
unseal: each is an ArgoCD `PreSync` hook Job templated into the consuming
chart (`gitops/charts/sql-schema`'s `-d0` "prerequisites" Application for
`mcp-sales-db`; `gitops/charts/rag-service`'s own `-d1` Application for
`rag`), with `hook-delete-policy: BeforeHookCreation` reproducing the
delete-then-recreate idiom Ansible previously did by hand (Jobs are
immutable). Only the static SQL/fixtures `ConfigMap` generation
(`ansible/roles/{sql_schema,rag}/kustomize/schema/`, plain
`configMapGenerator`s reading `data/{sxa,rag}/`) stays Ansible-applied -
these Jobs are not "standing installed components" any more than before,
but ArgoCD's resource-hook mechanism can express a one-shot, blocking,
re-run-on-every-sync action just as well as Ansible's own
delete/create/wait tasks could, without leaving it outside GitOps.

`nfd`, `nvidia_gpu`, `openshift_ai`, `external_secrets`, `smtp` and
`observability` used to be in an exception bucket like `argocd`'s above -
either an OLM `Subscription` + operator-managed CR, or (for `smtp`) a
static kustomize manifest, was judged to have no meaningful "chart" to
template through ArgoCD. ADR-0312 (and its later `-d0`/`-d1` extension)
reversed that: each now has its own `-d0`/`-d1` Application pair backed by
one chart with `operator.enabled`/`<operand>.enabled`-style Helm value
toggles (see `gitops/charts/README` per-chart docs) controlling which half
renders. The Subscription's health is gated by a custom ArgoCD health
check for `operators.coreos.com/Subscription` -
`ansible/roles/argocd/tasks/apply_resource_health_checks.yml` - which the
including role's `install.yml` waits on before applying `-d1`. `zuno-ai-run`'s
`Namespace`, its RHOAI dashboard label and its GPU `ResourceQuota` (formerly
duplicated across `openshift_ai`'s and `external_secrets`' own kustomize)
are owned by `gitops/charts/namespaces` instead, closing that
double-ownership.

`cert-manager` is a brand-new Day 0 component (not a conversion of an
existing kustomize path) following the exact same `-d0`/`-d1` shape: `-d0`
installs the operator (plus its own singleton `CertManager` config CR,
the same "meta-operator needs a CR to actually deploy pods" pattern as
`external_secrets`' `OperatorConfig`); `-d1` applies a `ClusterIssuer`
backed by a `pki/` secrets engine `ansible/roles/vault` prepares (see that
role's README). Infrastructure only for now - no existing Route/service
consumes this issuer yet.

**Vendored startx charts**: `nfd`, `nvidia-gpu`, `openshift-ai`,
`cert-manager`, `keycloak`, `postgresql`, `connectivity-link`, `lws`,
`jobset`, `external-secrets`, `custom-metrics-autoscaler`, `kiali`,
`mesh-monitoring`, `observability` and `tempo` vendor a chart from the
[startx `helm-repository`](https://helm-repository.readthedocs.io) as a
Helm `dependencies:` entry (same pattern `gitops/charts/vault` already used
for `hashicorp/vault`), instead of hand-authoring their own Namespace/
OperatorGroup/Subscription boilerplate - `helm dependency update` vendors
the chart's `.tgz` (gitignored, resolved at render time) and pins its
version in a committed `Chart.lock`. Only the genuinely Zuno-specific
content (the `CertManager`/`ClusterIssuer` CRs, the Keycloak CR/RealmImport/
ExternalSecrets, the PostgresCluster/pgvector wiring, the discovered
`ClusterPolicy`/`DataScienceCluster` specs, the various operand CRs -
`Kuadrant`/`KedaController`/`Kiali`/`OSSMConsole`/`MonitoringStack`/
`OpenTelemetryCollector`/`TempoMonolithic`/`OperatorConfig`/
`ClusterSecretStore`) stays as local templates in these charts.
`nfd`/`nvidia-gpu`/`openshift-ai`/`cert-manager` use that component's
matching `cluster-xxx` chart (`cluster-nfd`/`cluster-gpu`/`cluster-ods`/
`cluster-certmanager`), which already bundles startx's own
`project`+`operator` dependencies; every other chart in that list instead
depends directly on the generic `operator` chart (plus `project` when a
dedicated Namespace is needed) since no matching `cluster-xxx` bundle is
known to exist for any of those operators (ADR-0317) - see each chart's
`Chart.yaml`/`values.yaml` for the specific reasoning. `connectivity-link`/
`jobset`/`lws`/`external-secrets` subscribe into the shared
`openshift-operators` namespace (`AllNamespaces`, no `project`/
`OperatorGroup` dependency - relies on OLM's own global OperatorGroup
there); `connectivity-link` still depends on `project` for its Kuadrant
operand namespace (`kuadrant-system`) on the `-d1` side.
`custom-metrics-autoscaler`/`kiali`/`mesh-monitoring`/`observability`/
`tempo` depend on both `project` and `operator` for a dedicated operator
namespace + `OperatorGroup`. `vault` was evaluated against `cluster-vault`
and deliberately NOT migrated: its own `project` dependency isn't needed
(`zuno-data` is already created by `gitops/charts/namespaces`), and
adopting it would force an unrelated, unreviewed `hashicorp/vault` chart
version jump (0.28.1 → 1.21.2) for no offsetting benefit.

**`Namespace` resources on the `-d0` side**: every chart that declares its
own `Namespace` (the operator's dedicated namespace, or - for
`cert-manager`/`external-secrets` - a second namespace beyond it, or -
for `namespaces` - the whole set of platform/agent namespaces) renders it
as an ArgoCD `PreSync` hook (`argocd.argoproj.io/hook: PreSync`), not a
`sync-wave`'d resource. A hook runs in its own phase, entirely before the
normal Sync phase, so its existence relative to everything else in the
same chart (`OperatorGroup`/`Subscription`/`ResourceQuota`/...) is
guaranteed - `sync-wave` only orders resources *within* the same Sync
phase, not against a separate namespace-creation concern. No
`hook-delete-policy` is set, so the `Namespace` persists across
re-syncs and is only removed when the Application itself is deleted.

Independently, every `-d0` Application's `syncOptions.CreateNamespace` is
`true` whenever its own `spec.destination.namespace` isn't already
guaranteed to exist some other way (a dedicated operator namespace no
earlier `day0_components` role creates - `cert-manager`, `external-secrets`,
`nfd`, `nvidia-gpu`, `openshift-ai`, `observability`, and `namespaces`
itself for `zuno-ai-run`) - `false` (the default) everywhere else,
including every `-d0` whose destination is created by `gitops/charts/
namespaces` ahead of it in `day0_components` (`keycloak`, `postgresql`,
`smtp`) and every no-op `-d0` (`destination.namespace: openshift-gitops`,
which always exists). Where both apply to the same namespace (e.g.
`cert-manager-operator`), they're deliberately redundant safeguards, not
alternatives.

`keycloak` and `postgresql` were never in the exception bucket above -
their operand (`Keycloak`+`KeycloakRealmImport`, `PostgresCluster`) was
always declarative here - but their operator `Subscription` (+
`OperatorGroup` for `keycloak`) was, the same split `postgresql`'s own
image build docs call out. ADR-0312 folded those in too, as a follow-up
once the health-check mechanism existed, later split into their own
`-d0`/`-d1` pairs the same way as the six components above.

Directories present:

| Component | Source |
|---|---|
| `admin-context` | local chart, `gitops/charts/admin-context` (ADR-0314 - `-d0`: the four zuno `PriorityClass` objects, `priorityClasses.enabled`; `-d1`: the `startx` `HelmChartRepository`, `helmChartRepository.enabled`) - no operator, both halves are cluster-scoped |
| `vault` | local chart, `gitops/charts/vault` (wraps Helm chart `hashicorp/vault` as a dependency) - no operator, `-d0` is a no-op |
| `cert-manager` | local chart, `gitops/charts/cert-manager` (`-d0`: startx `cluster-certmanager` dependency for Namespace/OperatorGroup/Subscription + local `CertManager` config CR; `-d1`: Vault-backed `ClusterIssuer` - see the `cert_manager` role's README) |
| `keycloak` | local chart, `gitops/charts/keycloak` (`-d0`: startx `operator` dependency for the RHBK `Subscription`/`OperatorGroup` - not `cluster-sso`, see that chart's Chart.yaml; `-d1`: Keycloak CR/RealmImport/ExternalSecrets - ADR-0312, see the `keycloak` role's README) |
| `postgresql` | local chart, `gitops/charts/postgresql` (`-d0`: startx `operator` dependency for the PGO `Subscription` - not `cluster-crunchy`, see that chart's Chart.yaml; `-d1`: PostgresCluster/ExternalSecret/ConfigMap - ADR-0312, see the `postgresql` role's README) |
| `models` | local chart, `gitops/charts/models` (KServe ServingRuntime + InferenceService) - no operator, `-d0` is a no-op |
| `mcp` | local chart, `gitops/charts/mcp-gateway` - no operator, `-d0` is a no-op |
| `rag` | local chart, `gitops/charts/rag-service` - no operator, `-d0` is a no-op |
| `ai-gateway` | local chart, `gitops/charts/ai-gateway` (applied by the `llm` role, see its README; ADR-0009) - no operator, `-d0` is a no-op |
| `agent-runtime` | local chart, `gitops/charts/agent-runtime` (applied by the `llm` role, see its README) - no operator, `-d0` is a no-op |
| `namespaces` | local chart, `gitops/charts/namespaces` (`-d0`: Namespace objects, `namespace.enabled`; `-d1`: ResourceQuota/NetworkPolicy scaffolding, `policy.enabled` - spans the macro Day 0/Day 1 split, not just this component's own internal ordering) |
| `api` | local chart, `gitops/charts/tekos` - no operator, `-d0` is a no-op |
| `llm` | native Kustomize app, `platform/ai-gateway/` (provider routing ConfigMap + provider `ExternalSecret`s) - no operator, `-d0` is a no-op |
| `mcp-sales-db` | local chart, `gitops/charts/mcp-sales-db` (applied by the `sql_schema` role, after its schema/fixtures Job) - no operator, `-d0` is a no-op |
| `nfd` | local chart, `gitops/charts/nfd` (ADR-0312 - `-d0`: startx `cluster-nfd` dependency, entirely - Namespace/OperatorGroup/Subscription; `-d1`: `cluster-nfd`'s own NodeFeatureDiscovery CR) |
| `nvidia-gpu` | local chart, `gitops/charts/nvidia-gpu` (ADR-0312 - `-d0`: startx `cluster-gpu` dependency for Namespace/OperatorGroup/Subscription; `-d1`: `cluster-gpu`'s own ClusterPolicy CR, spec injected once discovered - see that chart's README) |
| `openshift-ai` | local chart, `gitops/charts/openshift-ai` (ADR-0312 - `-d0`: startx `cluster-ods` dependency for Namespace/OperatorGroup/Subscription; `-d1`: `cluster-ods`'s own DataScienceCluster CR, spec overridden in full - RawDeployment, not startx's Serverless-dependent default) |
| `external-secrets` | local chart, `gitops/charts/external-secrets` (ADR-0312 - `-d0`: startx `operator` dependency for the `Subscription` into `openshift-operators` (`AllNamespaces`, no `OperatorGroup`), plus local `OperatorConfig`; `-d1`: ClusterSecretStore/cluster-domain ExternalSecret, rendered only once the discovered Vault Service name is supplied - see the `external_secrets` role's README) |
| `smtp` | local chart, `gitops/charts/smtp` (`-d0`: zuno-ai-run Namespace; `-d1`: technical mail identity ExternalSecret) - no operator |
| `observability` | local chart, `gitops/charts/observability` (`-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-opentelemetry-operator` Namespace/OperatorGroup/Subscription; `-d1`: shared OTLP Collector, exporting to both `debug` and `tempo`'s `otlp/tempo`) |
| `service-mesh` | local chart, `gitops/charts/service-mesh` (`-d0`: startx `cluster-istio` dependency, `operatorIstio.enabled`, installs the servicemeshoperator3/Sail Operator; `-d1`: Vault-backed mesh CA (`clusterIssuer`/`istioCsr`), `istiocni` and the `istio` control plane itself, in zuno-mesh) |
| `connectivity-link` | local chart, `gitops/charts/connectivity-link` (ADR-0317 - `-d0`: startx `operator` dependency for the `Subscription` into `openshift-operators` (`AllNamespaces` - the operator's CSV doesn't support `OwnNamespace`, confirmed against a real cluster), no `OperatorGroup`; `-d1`: startx `project` dependency for the dedicated `kuadrant-system` Namespace + minimal empty `Kuadrant` operand CR) |
| `lws` | local chart, `gitops/charts/lws` (ADR-0317 - `-d0`: startx `operator` dependency for the `Subscription` into `openshift-operators` (`AllNamespaces`, same shape as `connectivity-link` after its fix), no `OperatorGroup`/dedicated `Namespace`; `-d1` is a no-op, no singleton operand CR exists for LeaderWorkerSet) |
| `custom-metrics-autoscaler` | local chart, `gitops/charts/custom-metrics-autoscaler` (ADR-0318 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-keda` Namespace/OperatorGroup/Subscription (`OwnNamespace`, per Red Hat's documented install procedure); `-d1`: minimal `KedaController` operand CR) |
| `jobset` | local chart, `gitops/charts/jobset` (ADR-0318 - `-d0`: startx `operator` dependency for the `Subscription` into `openshift-operators` (`AllNamespaces`), no `OperatorGroup`; `-d1` is a no-op, no singleton operand CR exists for JobSet) |
| `tempo` | local chart, `gitops/charts/tempo` (ADR-0312 - `-d0`: startx `project`+`operator` dependencies for the dedicated `openshift-tempo-operator` Namespace/OperatorGroup/Subscription; `-d1`: demo-scale `TempoMonolithic` in zuno-telemetry, storing traces exported by `observability`'s Collector) |
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
real deployment. Because `gitops_app_extra_helm_values` (ADR-0048) replaces
`spec.source.helm.values` wholesale rather than merging with it, any role
that both needs this substitution *and* sets extra Helm values (currently
`keycloak`'s `-d1` apply) must re-supply `clusterBaseDomain` itself from the
already-resolved `cluster_base_domain` fact - see that role's
`tasks/install.yml`. `ansible/roles/external_secrets` also exposes that
Vault value as a `zuno-cluster-domain` Secret in `zuno-ai-run` for any
service that wants it as a live runtime value rather than a
Helm-render-time one (not yet consumed by any service - the value only
reaches K8s manifest spec fields like a Route's `spec.host` or the Keycloak
CR's `spec.hostname.hostname` through the Ansible/Helm path, since those
fields have no `secretKeyRef`-style mechanism to source from a Secret).
