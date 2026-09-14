# ADR-0559: Follow the cluster's version and never branch the repository by OCP version

- **Status:** Accepted
- **Target:** v0.9
- **Date:** 2026-09-14
- **Decision owners:** Zuno Demo architecture team
- **Extends:** ADR-0048 (discover operator channels at deployment time), ADR-0558 (tolerate catalogs that stop publishing an installed operator)

## Context

`demo222` now runs OCP 5.0.0-rc.2, an unfinished Tech Preview. Its three
CatalogSources moved to the `:v5.0` indexes, which are markedly poorer than
their predecessors: 86 packages in `redhat-operators`, 85 in
`certified-operators`, 261 in `community-operators`. Thirteen Subscriptions
name a package their own catalog no longer publishes, and three more resolve
to a version *older* than the one installed or collide with a same-named
community package that is a different operator entirely. ADR-0558 records how
the repository now tolerates that state and reports it through probe P8; it
deliberately does not repair it, and it defers the underlying upgrade policy
to "its own record". This is that record.

The question put to the team was whether to branch the repository by OCP
version — `ocp-4.22` and `ocp-5.0` — and run `demo222` from one and `demo333`
from the other. Three measurements settle it.

**The clusters deploy from `main`, not from their branch.** On `demo222`, 110
of the 119 ArgoCD Applications carry `targetRevision: main`; the nine
exceptions point at a third-party Helm repository on its own `devel` branch.
`origin/demo333` is identical to `origin/main`, and `origin/demo222` is `main`
plus the commits currently in flight, destined to fast-forward. The
per-cluster branches are **workspaces**, not deployment targets. A branch per
OCP version would therefore create two divergent deployed trunks, each
requiring every fix to be ported twice, and would dissolve the
branch-validate-fast-forward flow that structures all parallel work.

**The index version is not an artefact of this repository.** The three
CatalogSources carry `operatorframework.io/managed-by: marketplace-operator`,
and `OperatorHub/cluster` runs with the default sources (`sources: null`,
`disableAllDefaultSources` unset). The `:v5.0` tag is derived from the
cluster's own version by the marketplace operator. A search for
`operator-index` across the entire repository returns nothing. Changing git
branch would therefore change nothing about which index a cluster consults —
the lever is not in git.

**The repository already absorbs divergence between clusters.** ADR-0048
established discovery over hardcoding. `gitops/charts/models/templates/maas.yaml`
already gates a resource on `.Capabilities.APIVersions.Has`, because the
`ModelsAsService` CRD survives on `demo222` (upgraded through 3.5.0-ea.2) and
is absent on a from-scratch GA install. `zuno_openshift_ai_version` in
`ansible/confidential.yml` pins a version for one cluster with, in the words
of the role's own diagnostic, "no chart edit and no live change to other
clusters". ADR-0558 added tolerance for the package that vanishes. One chart
already serves two clusters of different topology, without a branch.

A caution worth recording, because it nearly changed this decision: a
measurement reporting `demo333` as also running 5.0.0-rc.2 turned out to have
been taken against `demo222`. The kubeconfig on the shared workstation holds
contexts for both clusters, and its current context points at `demo222`, so
any command issued without an explicit `--context` silently answers for the
wrong cluster. `demo333` is in fact powered off — its API does not accept a
TCP connection — and its OCP version is, as of this record, **reported as
4.22 but unverified**.

## Decision

**The repository is never branched by OCP version.** One trunk. Per-cluster
branches remain short-lived workspaces that fast-forward into `main`, and
carry work in progress, never a permanent version fork.

**Version divergence is carried by cluster data, never by git topology.**
Three levers, in order of preference: a Helm `.Capabilities` gate when the
difference is the presence of an API or CRD; a per-cluster Ansible variable
when it is a version or a toggle; ADR-0558's tolerance when a catalog stops
serving a package. Reach for a fourth mechanism only after establishing that
none of the three fits.

**Restoring an update path is a catalog operation, not a repository one.**
When an operator must regain an upgrade path on a cluster whose default index
no longer serves it, the remedy is an **additional CatalogSource pinned to an
index that does**, added alongside the default sources and never replacing
them, rendered by a chart and enabled per cluster. Two constraints bind it:
every Subscription must name its `source` explicitly, because the same
package name exists in several indexes at different versions and resolves to
different operators; and the objective is to restore a *path*, never to
travel it — adding a source must not produce an unapproved InstallPlan.

**This last decision is gated on a measurement that has not been taken.** It
assumes the `:v4.22` indexes still serve the packages `:v5.0` dropped, which
could not be confirmed: `oc image info` on that index is unauthorized from the
workstation. `demo333`, if it is indeed still on 4.22, answers the question at
its next power-on for the cost of three read-only commands, and simultaneously
establishes whether the empty-status Subscriptions are a 5.0-only symptom. **No
additional CatalogSource is created before that measurement.**

**`startingCSV` is pinned where crossing a minor version unattended is
unacceptable, and the known-good set is recorded as data.** ADR-0558 observed
that recovering from a freeze moved `mariadb-operator` from v26.3.0 to
v26.6.0 because almost nothing pins `startingCSV`. Pinning every operator is
rejected — it would re-hardcode what ADR-0048 removed. Instead, the set of
versions known to work on a given OCP version is recorded as data under
`platform/`, and `startingCSV` is set only for the operators whose unattended
minor-version drift is judged unacceptable. The data file makes a rebuild
reproducible; the pins make a recovery predictable.

## Consequences

A cluster's OCP version becomes an input to the deployment rather than a
property of a branch, which is what allows one trunk to serve a Tech Preview
cluster and a stable one at the same time. The fleet strategy the team
wanted — one cluster absorbing the 5.0 Tech Preview while another stays on a
stable release — needs no repository change at all: it is already true if
`demo333` remains on 4.22.

The cost is that divergence becomes invisible in git. Nothing in a diff says
"this renders differently on 4.22", and the capability gates that encode it
are scattered across the charts that need them. Probe P8 and the known-good
version set are what keep that legible; without them the arrangement degrades
into undocumented per-cluster drift.

Fourteen operators on `demo222` remain without an upgrade path until either
the `:v5.0` indexes publish them again or an additional CatalogSource is
added under the gate above. That includes security fixes. This is an accepted,
temporary risk, and the exit criterion is explicit: **when the `:v5.0` indexes
serve those packages again, any additional CatalogSource is removed and this
decision's third clause becomes inert.**

## Security considerations

Fourteen operators, among them the GitOps, SSO, signing and database
operators, cannot currently receive a fix of any kind on `demo222`. That is
the principal risk this record accepts, and the reason the exit criterion is
stated rather than left implicit.

An additional CatalogSource widens the set of images a cluster may install
from. Only Red Hat-operated indexes are admissible under this decision;
pointing a CatalogSource at a third-party or self-built index is out of its
scope and would need its own record. Because a same-named package can resolve
to a different operator depending on the index, a Subscription that omits its
`source` is a supply-chain hazard, not merely an ambiguity.

## Operational considerations

Any command issued against a cluster from the shared workstation must pass
`--context` explicitly. The current context points at `demo222`, and a
command without it answers for `demo222` whatever cluster the operator
believes they are addressing — an error that has already produced false
measurements and nearly amended a vendor defect report.

Probe P8 already reports frozen Subscriptions. Verifying this decision needs
no new tooling: after any catalog change, the five Subscriptions with an empty
`status` must regain an `installedCSV`, the three Applications stuck
`Progressing` must return to `Healthy`, and `oc get installplan -A` must show
no new unapproved plan.
