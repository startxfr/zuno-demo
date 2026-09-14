# ADR-0558: Tolerate catalogs that stop publishing an installed operator

- **Status:** Implemented
- **Target:** v0.9
- **Date:** 2026-09-14
- **Decision owners:** Zuno Demo architecture team
- **Extends:** ADR-0048 (discover operator channels at deployment time)

## Context

ADR-0048 established that this repository never hardcodes an operator's
catalog or channel: every operator-backed role looks the package up in a
`PackageManifest` and feeds the result into the `-d0` Subscription values.
It also ruled that a missing capability must "fail with a clear
diagnostic". Fourteen roles implement that, each with its own near-identical
copy of the lookup, and each failing hard when the lookup returns nothing.

That rule was written for a first install against a catalog that never
carried the package. It turns out to be wrong for a case ADR-0048 did not
anticipate: a catalog that carried the package, was used to install the
operator, and then **stopped carrying it**.

The upgrade of `demo222` to OCP 5.0.0-rc.2 replaced the three
CatalogSources with the `:v5.0` indexes, which are markedly poorer than
their predecessors. Thirteen Subscriptions cluster-wide now name a package
their own catalog no longer publishes — `rhtas-operator`,
`crunchy-postgres-operator`, `rhcl-operator`, `dns-operator`,
`limitador-operator`, `rhods-operator`, `lightspeed-operator`, `nfd`,
`gpu-operator-certified`, `openshift-gitops-operator`,
`policy-controller-operator`, `ansible-automation-platform-operator` and
`rhbk-operator`. Every one of their CSVs is `Succeeded` and every operator
works. Nothing is broken; nothing is updatable either.

Two consequences, neither of which anything in this repository reported.

**A hard failure disproportionate to the loss.** A missing `PackageManifest`
only costs the `-d0` Subscription its discovered catalog and channel. The
operator is already installed and its Subscription already carries both.
But the `fail` sat at the top of the role, so the whole role died —
including the `-d1` operand configuration this repository owns and which has
nothing to do with catalogs. `make d1 install rhtas` was unusable on a
cluster whose RHTAS was running perfectly.

**A namespace-wide resolution freeze.** This is the sharp one. OLM resolves
a namespace as a unit: a single unsatisfiable Subscription makes *every*
`InstallPlan` in that namespace unresolvable, including one for a brand-new
operator with no relationship to it. During WP-143's flip back to internal
MariaDB, `mariadb-operator` produced no InstallPlan at all — because
`crunchy-postgres-operator`, `rhcl-operator` and `rhtas-operator` share
`openshift-operators` with it and could not resolve. Nothing about MariaDB
was wrong. The only visible symptom was an ArgoCD Application stuck
`Progressing` on "Waiting for OLM to install the Subscription's CSV", which
points at the wrong component entirely. Recovering it took pausing three
Applications' auto-sync, deleting the orphaned Subscriptions, nudging the
resolver and restoring everything — and the operator came back as
**v26.6.0 where v26.3.0 had been**, since almost nothing in this repository
pins `startingCSV`.

Worse, the state is indistinguishable from health by the obvious check: all
thirteen Subscriptions report `AtLatestKnown`, which means "no candidate in
the channel", not "up to date". On a poor index the two are the same string.

Pinning the catalog indexes was considered and rejected: this repository
deliberately does not manage CatalogSources (the single exception is
postgresql's community fallback), the indexes follow the OCP version, and
pinning them would trade a silent freeze for a silent divergence from the
platform the cluster actually runs.

## Decision

**A missing `PackageManifest` is fatal only when the operator is not already
installed.** When the package is absent but a Subscription for it exists,
the role skips its `-d0` apply — that Application keeps its last synced
values, so the Subscription is left exactly as it is — and proceeds with
everything else it owns. When both are absent it is a genuine first install
against the wrong catalog, and it still fails with ADR-0048's clear
diagnostic.

**The lookup is a shared task, not fourteen copies.**
`ansible/tasks/resolve_operator_package.yml` performs the discovery, the
existing-Subscription fallback and the channel selection, and exports
`operator_package_catalog`, `operator_package_channel` and
`operator_package_skip_d0`. Callers pass the package name and, where it
differs, the Subscription's namespace — eight operators subscribe outside
`openshift-operators`, and a fallback that looks in the wrong namespace
would reintroduce the hard failure it exists to prevent.

**The freeze is reported, not repaired.** `check_cluster_readiness.yml`
gains probe P8: every Subscription is compared against the packages its own
catalog serves, and the namespaces where other Subscriptions are blocked
alongside it are named explicitly. The comparison is `package@catalog` and
never the package name alone, because `community-operators` publishes
`limitador-operator`, `dns-operator` and `authorino-operator` that are
**different operators** from Red Hat's, and matching on name would silently
declare an orphan healthy.

P8 is advisory, never blocking. The cluster runs correctly in this state,
and the remedy — drop the Subscription and forfeit that operator's update
path, or wait for the catalog to publish again — is an operator's decision.
A blocking finding would refuse every install on a cluster that is merely
frozen.

## Consequences

An index that stops publishing a package degrades to "this operator cannot
update" instead of "this component cannot be configured", and the loss is
stated rather than discovered. The duplicated discovery block disappears
from the twelve exact-name roles; `postgresql` keeps its own fuzzy variant
(it matches `/crunchy/i` across all packages and adds a community
CatalogSource fallback) and `service_mesh` keeps its static-pin validation,
both deliberately outside this task's contract.

Skipping the `-d0` apply means an Application keeps values discovered under
a previous catalog. That is the intended behaviour — they are the values
that installed the running operator — but it makes the Application's
rendered state a record of the past rather than of the current catalog, and
P8 is what makes that visible.

The absence of `startingCSV` pins remains unaddressed here: recovering from
a freeze can move an operator across minor versions, as `mariadb-operator`
v26.3.0 → v26.6.0 did. Pinning every operator is a larger decision about
upgrade policy and belongs in its own record.

## Security considerations

A frozen operator receives no updates, security fixes included, and
`AtLatestKnown` will not say so — which is precisely why P8 reports the
condition rather than leaving it to an operator's reading of a Subscription
status. The decision deliberately does not repoint an orphaned Subscription
at a same-named package in another catalog: that would silently replace a
Red Hat operator with a community one of the same name, which is a supply
chain substitution, not a recovery.

## Operational considerations

P8 appears in `make d0 check` and reports the affected Subscriptions, the
namespaces where the freeze blocks other operators, and what each choice
costs. When an InstallPlan never appears for an operator whose own package
is fine, the namespace's other Subscriptions are the first place to look.

## Implementation state

**Implemented (2026-09-14)**, commit `44f29c0b`, verified live on
`demo222`: P8 reports the thirteen Subscriptions and identifies
`openshift-operators` as the namespace where they block others. The shared
task is used by `aap`, `connectivity_link`, `custom_metrics_autoscaler`,
`external_secrets`, `jobset`, `keycloak`, `kueue`, `lightspeed`, `lws`,
`mariadb`, `rhtas` and `rhtas_config`. Executed as
[WP-144](../roadmap/work-packages/wp-144-olm-catalog-drop-tolerance.md).
