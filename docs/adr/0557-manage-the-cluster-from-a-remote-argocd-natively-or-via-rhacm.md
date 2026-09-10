# ADR-0557: Manage the cluster from a remote ArgoCD, natively or via RHACM

- **Status:** Accepted - the study concluded 2026-09-10 with its pick
  recorded (see Study); implementation awaits ADR-0352's argocd work
  package.
- **Target:** v0.9
- **Date:** 2026-09-10
- **Decision owners:** Zuno Demo architecture team

## Context

ArgoCD is this platform's number-one infrastructure piece: every other
component — Day 0 to Day 2 — is delivered as an ArgoCD Application that
Ansible applies (ADR-0311/0312), rendered from `gitops/charts/` against
git `main`. Today that ArgoCD is always ours: the `argocd` role installs
the openshift-gitops operator by raw kustomize
(`ansible/roles/argocd/kustomize/{operator,argocd,appproject,rbac}`),
creates the `zuno` AppProject and the Subscription-health Lua
customization, and every `gitops/apps/*/application-*.yaml` targets
`metadata.namespace: openshift-gitops` on the local cluster.

ADR-0352 (amended 2026-09-10) makes `argocd` a vital Tier-A component
whose external mode covers not just a pre-existing in-cluster instance
but a **remote** one: an ArgoCD this repo does not deploy, running on
another cluster, that declares our cluster as a destination and carries
the `zuno` AppProject and our Applications. ADR-0352 fixes what external
mode must assert; it deliberately delegates the *mechanism* here. Two
candidate mechanisms exist, and they differ enough — in registration
model, credential flow and operational ownership — that the choice
deserves its own record.

Real target environments motivate both: a customer platform team that
runs one central ArgoCD for its fleet, and a customer that runs Red Hat
Advanced Cluster Management, where GitOps integration is a supported,
first-class feature rather than something assembled by hand.

## Decision

This is a **study ADR**: it frames the two options, fixes the
evaluation criteria and the shared constraints, and defers the pick to
its own acceptance step. No implementation surface changes under this
ADR.

### 1. Option A — native remote ArgoCD

The remote instance manages our cluster through ArgoCD's own
cluster-registration model:

- **Cluster declaration**: a cluster Secret
  (`argocd.argoproj.io/secret-type: cluster`) in the remote instance's
  namespace, carrying our API server URL and a bearer token for a
  dedicated ServiceAccount created on our cluster with exactly the RBAC
  ArgoCD needs — the declarative equivalent of `argocd cluster add`,
  authored as a manifest rather than run as a CLI login.
- **AppProject and Applications**: the `zuno` AppProject and every
  `gitops/apps/*/application-*.yaml` are applied into the remote
  instance's namespace, with `spec.destination.server` pointing at our
  cluster's API URL instead of `https://kubernetes.default.svc`.
- **To replicate**: the Subscription-health Lua customization
  (`argocd-cm` resource customizations) and the repository declaration
  for this repo — both live in the remote instance's config, which we
  do not own; they become clause-7-style prerequisites the external
  check asserts, plus a handed-over configuration document.

### 2. Option B — RHACM

The customer's RHACM hub imports our cluster as a `ManagedCluster` and
its GitOps integration (`GitOpsCluster` + `Placement`) registers the
managed cluster into the hub's ArgoCD automatically:

- **Cluster declaration**: RHACM's import flow (klusterlet agent)
  replaces the hand-built cluster Secret and ServiceAccount — the
  `GitOpsCluster` CR projects every `Placement`-selected managed
  cluster into ArgoCD as a destination, credentials handled by the
  hub. This is the mechanism's main draw: the registration problem
  Option A solves by hand is a supported product feature.
- **AppProject and Applications**: unchanged in shape — our
  Applications land in the hub's ArgoCD with the managed cluster as
  destination; whether via plain Applications or an ApplicationSet
  with a cluster generator is part of the study.
- **To study**: how much of the hub (ManagedCluster naming, Placement,
  the ArgoCD instance RHACM wires up) we may assert versus must simply
  document; and whether the klusterlet's footprint on our cluster
  collides with anything this repo owns.

### 3. Shared constraints, whichever option wins

- `ansible/tasks/apply_gitops_app.yml` remains the only path that
  applies Applications, but must gain a **target**: in external-remote
  mode it authenticates against the cluster hosting ArgoCD (a second
  kubeconfig/token in `confidential.yml`, per ADR-0352's schema
  discipline), while the `apps.mycluster.example.com` substitution
  continues to resolve against *our* cluster's Ingress domain.
- Network reachability is bidirectional and asserted, not assumed: the
  remote ArgoCD (or hub) must reach our API server; nothing on our
  side may need to reach into the remote instance beyond what `check`
  verifies.
- ADR-0352 clause 11 (dependency abstraction) applies unchanged: no
  chart or role branches on where ArgoCD lives; the Applications
  themselves are byte-identical between internal and external-remote
  modes except for `destination.server`.
- The ADR-0352 clause-10 vital gate applies: whichever mechanism is
  chosen, Day 1 does not start until the remote instance demonstrably
  syncs our Day-0 Applications.

### 4. Evaluation criteria for the pick

Simplicity of cluster registration and credential rotation; how much
remote-side configuration we can assert versus must document;
selfHeal/pruning ownership clarity (ADR-0346's OAuth fight is the
named failure mode to avoid); blast radius of a hub/remote outage on
our Day 0–2 verbs; and parity of the `make d0 check` experience across
internal, external-in-cluster and external-remote. RHACM enters the
study as the presumed-simpler path for exactly the registration and
credential concerns Option A handles by hand — presumed, to be proven.

## Study (2026-09-10)

Documentary study (no RHACM hub was available; sources below), crossed
with the repo constraints inventoried the same day: the `zuno`
AppProject carries no `roles:` block, all 112 Applications pin
`destination.server: https://kubernetes.default.svc` and
`metadata.namespace: openshift-gitops` (hardcoded 18 more times across
the gitops task files), auth is one ambient kubeconfig
(`load_k8s_auth_env.yml`), and the Subscription-health Lua lives on the
operator-managed ArgoCD CR — so externalizing it needs write access to
the *remote* CR, not just to an AppProject.

**What the research established.**

- *RHACM push model* — a `GitOpsCluster` resource referencing a
  `Placement` makes the GitOps cluster controller create the ArgoCD
  cluster Secrets automatically for every selected `ManagedCluster`, in
  the hub's ArgoCD namespace; ApplicationSets then target the fleet.
  This is exactly the registration-and-credential problem Option A
  solves by hand, done by a supported controller — label-selected
  clusters join ArgoCD as they are imported. The hub still *pushes*:
  it holds reconciliation and (via the klusterlet-backed integration)
  effective mutating power over every spoke, so a hub compromise or
  outage has fleet blast radius.
- *RHACM pull model* (Argo CD application pull controller /
  `argocd-agent` integration) — the hub wraps Applications in
  `ManifestWork`; the managed cluster's agent pulls them and a **local
  OpenShift GitOps (≥ 1.9) on each managed cluster** reconciles.
  **This rules the pull model out of ADR-0352's external mode**: it
  requires the very in-cluster ArgoCD external mode exists to remove.
  It is re-classified by this study as a possible future
  fleet-distribution layer *on top of internal mode*, not a candidate
  here.
- *Native Option A* — everything the RHACM push model automates is
  hand-built (cluster Secret, ServiceAccount + RBAC on our cluster,
  token rotation ours), but everything is also *assertable* with
  nothing but ArgoCD API access, and the trust grant is a
  ServiceAccount we scope and rotate — not a klusterlet.

**Against the clause-4 criteria.** Registration and credential rotation:
RHACM push wins outright (automatic, product-supported). Assert vs
document: native wins — the clause-7 assertions hold with a plain
token, where RHACM leaves ManagedCluster/Placement health partly
observable-only. Ownership clarity: equivalent once registered (both
end as a cluster destination in a remote ArgoCD; the Lua customization
and repo declaration are handed-over configuration in both). Blast
radius: same for both push variants — the remote instance is the single
sync engine, which is inherent to ADR-0352's external-argocd semantics.
Security: native's SA token is narrower than the
cluster-admin-equivalent klusterlet; RHACM is acceptable only where the
hub already sits inside the cluster's trust domain — which is precisely
the customer situation that motivates it.

**The pick (recommended).** Both push mechanisms, behind one sub-mode
key — `zuno_argocd_external_flavor: native | rhacm` — with **rhacm
preferred wherever a hub already manages the cluster** (the
registration/credential machinery is the hard part, and there it is the
product's job), and **native as the general case** (no hub required,
fully assertable, narrowest credential). The clause-7 assertions stay
identical for both (AppProject, Lua health check, repo declaration,
cluster declared); only the *how it got registered* differs, so the
`argocd` role asserts the result and documents per-flavor prerequisites
rather than driving hub objects. The RHACM pull model is out of scope
for external mode, recorded above. Implementation lands under a future
work package once ADR-0352's pilot chain reaches argocd (its clause 9
places argocd last).

Sources: [RHACM with OpenShift GitOps (Red Hat blog)](https://www.redhat.com/en/blog/red-hat-advanced-cluster-management-with-openshift-gitops),
[RHACM 2.13 GitOps documentation](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/2.13/html-single/gitops/index),
[Argo CD Application Pull Controller (Red Hat blog)](https://www.redhat.com/en/blog/introducing-the-argo-cd-application-pull-controller-for-red-hat-advanced-cluster-management),
[open-cluster-management-io/argocd-pull-integration](https://github.com/open-cluster-management-io/argocd-pull-integration),
[Integrate RHACM with Argo CD (Red Hat Developer, 2026-03)](https://developers.redhat.com/articles/2026/03/24/integrate-red-hat-advanced-cluster-management-argo-cd).

## Consequences

- ADR-0352's `zuno_argocd_external_*` schema gains whichever keys the
  chosen mechanism needs (a hub kubeconfig reference, or a remote
  ArgoCD namespace + token); the schema change lands as an ADR-0352
  progress note, not a second vocabulary.
- The `argocd` role grows an assert-external personality per ADR-0352
  clause 4; in RHACM mode part of that assertion moves to hub-side
  objects we can only observe.
- Until this study concludes, ADR-0352's argocd external mode is
  implementable only for the in-cluster case; the pilot ordering in
  its clause 9 already places argocd last for this reason.

## Security considerations

Both options hand a remote system standing credentials to mutate this
cluster — the inverse of every other ADR-0352 external mode, where we
hold credentials to a remote service. Option A's ServiceAccount token
is scoped by us and rotatable by us; RHACM's klusterlet holds
cluster-admin-equivalent power by design, which is acceptable only
where the hub is inside the same trust domain as the cluster. The
study must state, per option, who can rotate what and what a
compromised hub/remote instance can reach.

## Acceptance criteria

- This ADR exists with both options framed, the shared constraints and
  the evaluation criteria above.
- The `## v0.9` index table in `docs/adr/README.md` has the ADR-0557
  row and its status matches the body.
- No implementation surface has changed under `ansible/` or `gitops/`.
- The pick itself — Option A, Option B, or both behind a sub-mode key —
  is recorded as a dated progress note in this ADR before any
  implementing work package is authored.

See [Standard clauses](README.md#standard-clauses) for Alternatives,
Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0311](0311-stop-applying-the-root-app-of-apps-from-ansible.md)
- [ADR-0312](0312-route-operator-installs-through-argocd-applications.md)
- [ADR-0346](0346-trust-the-ingress-router-ca-and-absorb-the-startx-cluster-auth-oauth-settings.md)
- [ADR-0352](0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- [ADR-0547](0547-parameterize-every-cluster-specific-value-in-ansible.md)
- [ADR-0556](0556-introduce-a-zuno-operator-with-foundation-infra-and-stack-crds.md)
