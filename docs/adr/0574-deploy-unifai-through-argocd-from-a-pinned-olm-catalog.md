# ADR-0574: Deploy UnifAI through ArgoCD from a pinned OLM catalog

- **Status:** Implemented
- **Target:** v0.11
- **Date:** 2026-10-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0559](0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md) (follow the cluster's version and never branch by OCP version)
- **Related:** [ADR-0048](0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md), [ADR-0535](0535-adopt-rhtas-as-the-artifact-trust-and-supply-chain-service.md), [ADR-0557](0557-manage-the-cluster-from-a-remote-argocd-natively-or-via-rhacm.md), [ADR-0558](0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md), [ADR-0561](0561-adopt-unifai-as-the-agent-platform.md), [ADR-0562](0562-authenticate-unifai-against-the-zuno-keycloak-realm.md), [ADR-0560](0560-keep-the-ai-gateway-as-the-policy-router-in-front-of-unifai.md), [ADR-0564](0564-deliver-okf-bundles-to-unifai-operator-as-signed-oci-artifacts.md), [ADR-0575](0575-upstream-generic-unifai-changes-and-isolate-zuno-specific-code.md)

## Context

UnifAI is deployed by the fork's operator, `unifai-operator`
(`fork/unifai-operator`, Go, group `unifai.startx.fr/v1alpha1`, version
0.1.12). The operator embeds the upstream Helm charts and installs a whole
stack from one `UnifaiStack` named `unifai` per namespace, then pushes
object kinds (`UnifaiLLM`, `UnifaiProvider`, `UnifaiTool`, `UnifaiAgent`,
`UnifaiWorkflow`, ...) into the stack through its REST API; objects wait
while their stack is not Ready (`fork/unifai-operator/README.md`).

Its distribution today is built for iteration, not for a governed platform:

- the catalog image is published only as
  `quay.io/zuno/unifai-operator-catalog:latest`, and the CatalogSource polls
  it every 15 minutes (`deploy/olm/catalogsource.yaml`; the README states
  "The catalog image tag is `latest` and the CatalogSource polls it");
- the Subscription follows `alpha` with `installPlanApproval: Automatic`
  (`deploy/olm/subscription.yaml`), so any push to the catalog is rolled out
  by OLM. The fork's maintaining session confirms this on `demo333`, where
  one operator serves two stacks (`unifai-devel`, `unifai-olm`) and every
  pushed image reaches both;
- application images default to `quay.io/zuno/unifai-<component>:devel`, a
  mutable tag the fork's `MEMORY.md` already warns nodes cache, and
  `spec.images` overrides are split on the last `:` by `splitTag`
  (`internal/stack/plan.go`), so a digest reference has never been a tested
  input;
- the operator was installed by hand with `oc apply`, outside ArgoCD.

Zuno's rules for operators are explicit. ADR-0559 requires every
Subscription to name its `source`, and its security section limits
admissible CatalogSources to Red Hat-operated indexes, stating that a
third-party or self-built index "is out of its scope and would need its own
record". This is that record. ADR-0558 tolerates catalogs that stop
publishing an installed package. ADR-0535 signs first-party images with
RHTAS, and its Policy Controller's admission gate requires images referenced
by digest. Finally, the ArgoCD Application objects are not themselves
git-synced: Ansible roles write them through
`ansible/tasks/apply_gitops_app.yml`, so a component exists only when its
role and its `gitops/apps/<component>/application-d*.yaml` both do.

## Decision

**UnifAI is a zuno component like any other**: a chart
`gitops/charts/unifai`, Applications `gitops/apps/unifai/application-d0.yaml`
and `application-d1.yaml`, an Ansible role `ansible/roles/unifai` applying
them, and `make d0|d1 install|check|uninstall unifai`. Nothing is applied by
hand on a zuno cluster.

**Day 0 installs the operator from a pinned, self-built catalog.**

- A `CatalogSource` named `unifai-operator-catalog` whose image is a
  **version tag or digest**, never `latest`. With an immutable reference,
  `registryPoll` is omitted: the only way a new operator version reaches a
  cluster is a reviewed change of that reference in git.
- The default Red Hat sources are untouched; this source is added beside
  them, as ADR-0559 requires of any additional catalog.
- The Subscription names `source: unifai-operator-catalog` and
  `sourceNamespace` explicitly, follows `stable`, and sets `startingCSV`
  to the pinned version. `installPlanApproval: Automatic` is acceptable here
  because the pinned index cannot offer a version git did not choose.
- The operator stays in `openshift-operators` (AllNamespaces) as it is on
  `demo333` today, so no new OperatorGroup is created there; a dedicated
  namespace with its own OperatorGroup is used only if WP-151 finds a
  reason to scope it.
- ADR-0558's shared lookup (`resolve_operator_package.yml`) handles this
  package like any other, keyed `package@catalog`.

**Day 1 renders the stack, then the objects, in waves.**

1. Namespace, `ExternalSecret`s (OIDC client secret per ADR-0562, provider
   credentials, Qdrant key, stack secrets override from Vault), NetworkPolicy
   additions.
2. `UnifaiStack/unifai` with `spec.version` and every `spec.images` entry
   **pinned by digest**, `identity.external` on realm `zuno`, remote
   embeddings (ADR-0568), OTel export (ADR-0566), `exposure.exposeInternal`
   off, `deletionPolicy: Retain`. ArgoCD waits on the stack's Ready condition
   through a health check before the next wave.
3. Object CRs: `UnifaiLLM` and `UnifaiProvider` pointing at the ai-gateway
   (ADR-0560), then tools, retrievers and agents. The agent layer arrives
   through `UnifaiAgentBundle` (ADR-0564) rather than hand-written CRs.

CRs whose CRD is installed by the operator carry
`argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true`, as
`gitops/charts/openshift-ai/templates/ogxserver.yaml` already does.

**Images are first-party and signed like ours.** Operator, bundle, catalog
and the five application images are built from tagged fork releases
(ADR-0575), signed with the same RHTAS keyless flow and Vault Transit
fallback as the 14 Priority-1 zuno images (ADR-0535), and referenced by
digest. The fork's release targets gain an immutable version tag for the
catalog and record digests; until `splitTag` is proven to round-trip a
digest reference into every chart (WP-151, with a render test), digest
pinning of application images is a stated gap, not an assumption. The
third-party images the operator defaults to (Mongo, Qdrant, RabbitMQ,
Redis, Temporal, docling-serve) are pinned by digest through `spec.images`
as well.

**The same chart serves both clusters and a remote ArgoCD.** Per-cluster
values (hosts, storage classes, catalog reference) come from the Ansible
variables of ADR-0547 and ADR-0559's levers, never from a branch, and the
Applications follow the layout ADR-0557 assumes, so they move with the rest
if the cluster is later managed remotely.

## Consequences

UnifAI becomes reproducible from git: a rebuilt cluster gets exactly the
operator version and images recorded, and an upgrade is a commit that
changes one catalog reference and the stack's digests.

The fork's release flow gains work: a version-tagged catalog, recorded
digests, signatures. The convenient "push and OLM rolls it out" loop
remains available on the fork's own stacks only; zuno stacks no longer
follow it. On `demo333`, the hand-made CatalogSource and Subscription are
replaced by the chart's (WP-151), which moves `unifai-devel` and
`unifai-olm` onto the pinned version at the same time, because both are
served by the one cluster-wide operator.

A self-built catalog is a supply-chain surface zuno now owns, unlike the
Red Hat indexes ADR-0559 covers. ADR-0558's P8 probe reports it like the
others if it ever stops publishing the installed package.

## Security considerations

The operator runs cluster-wide with the rights to install Helm releases, a
Keycloak operator Subscription and NetworkPolicies. Its catalog is the
highest-value artifact in this chain: whoever can push a catalog image that
a cluster pulls can run code with those rights. Pinning the reference to a
digest or immutable tag, signing it, and removing `registryPoll` are what
make a compromised push inert until someone changes git.

Mutable `:devel` tags are never used on a zuno cluster. The Policy
Controller's digest gate (ADR-0535) is dormant today; this decision makes
UnifAI compatible with it rather than relying on it.

The chart must not create the public Routes the upstream charts define for
Mongo, Qdrant, Redis Insight and Temporal (fork `MEMORY.md`); the operator
already drops them unless `exposure.exposeInternal` is set, and the chart
never sets it.

## Operational considerations

Verify the pinning against a dead mechanism: after install, push a new
`latest` catalog image and confirm that no InstallPlan appears and the CSV
version is unchanged. A green Subscription proves nothing on its own.

Applications are written by the role, not synced from `gitops/apps/`; after
committing an Application change, run `make d1 install unifai` and check the
live object.

`demo333` is powered off at the time of writing; WP-151's live steps start by
asking the user to power it on. `demo222` receives this chart only at its
own cutover (ADR-0573). Every `oc` command passes `--context`.
