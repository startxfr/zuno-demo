# ADR-0557: Manage the cluster from a remote ArgoCD, natively or via RHACM

- **Status:** Proposed
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
