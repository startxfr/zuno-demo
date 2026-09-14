# WP-144: Tolerate and report catalogs that drop an installed operator

- **State:** Done (2026-09-14 - shared discovery task adopted by the twelve exact-name roles, readiness probe P8 live-verified on demo222 reporting 13 frozen Subscriptions and naming openshift-operators as the namespace where they block others)
- **ADRs:** [ADR-0558](../../adr/0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md)
- **Depends on:** none
- **Related:** [ADR-0048](../../adr/0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md), [ADR-0517](../../adr/0517-redeploy-the-full-platform-from-scratch-on-a-new-demo333-cluster.md), [WP-143](wp-143-mariadb-internal-external-pilot.md)
- **Target:** v0.9
- **Estimated files touched:** ~15 — a new `ansible/tasks/resolve_operator_package.yml`, `ansible/tasks/check_cluster_readiness.yml`, and the twelve `ansible/roles/*/tasks/install*.yml` that discover a package by exact name.

> Not a planned work package. It was opened by a live incident during
> WP-143's flip back to the internal MariaDB and executed in the same
> session, so this brief records what was found and what was changed rather
> than proposing work still to do.

## Goal

An index that stops publishing a package must degrade to "this operator
cannot update" instead of "this component cannot be configured", and the
namespace-wide resolution freeze that comes with it must be reported rather
than discovered by whoever tries the next install.

## What triggered it

`make d1 install mariadb`, run to recreate the internal MariaDB at the end
of WP-143's there-and-back rehearsal, wedged: `zuno-mariadb-d0` sat
`Progressing` on "Waiting for OLM to install the Subscription's CSV" and no
`InstallPlan` was ever created. Nothing about MariaDB was wrong. The
`mariadb-operator` package was published, its Subscription was correct, and
the same command had worked an hour earlier.

The cause was three *other* Subscriptions sharing `openshift-operators`:
`crunchy-postgres-operator`, `rhcl-operator` and `rhtas-operator`, whose
packages the OCP 5.0.0-rc.2 catalog indexes had stopped publishing. OLM
resolves a namespace as a unit, so one unsatisfiable Subscription blocks
every InstallPlan in it. A separate earlier symptom in the same session had
the same root: `make d1 install rhtas` hard-failed on its own missing
`PackageManifest` while RHTAS itself ran perfectly (fixed as a one-off in
`cfecd615`, generalised here).

## What was changed

**A shared discovery task.** `ansible/tasks/resolve_operator_package.yml`
performs the `PackageManifest` lookup, the existing-Subscription fallback
and the `stable`-else-`defaultChannel` selection, exporting
`operator_package_catalog`, `operator_package_channel` and
`operator_package_skip_d0`. The twelve roles that discover a package by
exact name now call it: `aap`, `connectivity_link`,
`custom_metrics_autoscaler`, `external_secrets`, `jobset`, `keycloak`,
`kueue`, `lightspeed`, `lws`, `mariadb`, `rhtas`, `rhtas_config`. Each had
carried a near-identical copy of the same five tasks; 588 lines of
duplication went with them.

`postgresql` and `service_mesh` were deliberately left alone — the first
matches `/crunchy/i` across every package and adds a CatalogSource fallback,
the second validates a static `startingCSV` pin. Both are different
contracts, not variants of this one.

**The readiness probe.** `check_cluster_readiness.yml` gains P8, which
compares every Subscription against the packages its own catalog publishes
and names the namespaces where the freeze blocks other Subscriptions.
Advisory, never blocking, per ADR-0558.

## Live findings

1. **The freeze is namespace-wide, not per-operator.** This is the finding
   that cost the time: the failing component and the causing component were
   unrelated, and the error text named only the failing one. The remedy on
   the day was to pause auto-sync on the three owning Applications, delete
   the orphaned Subscriptions (CSVs are unaffected), nudge the resolver,
   then restore both.

2. **`AtLatestKnown` does not mean up to date.** It means "no candidate in
   the channel", which on a poor index is indistinguishable from a total
   freeze — including for security fixes. Thirteen Subscriptions on
   `demo222` read `AtLatestKnown` while being unable to resolve anything.

3. **Recovering a freeze can move an operator across versions.**
   `mariadb-operator` came back as **v26.6.0 where v26.3.0 had been**,
   because almost no Subscription in this repository pins `startingCSV`
   (only `openshift-ai`, `service-mesh` and the raw-kustomize ArgoCD one
   do). Not addressed here; ADR-0558 records it as a separate decision
   about upgrade policy.

4. **Eight operators subscribe outside `openshift-operators`** — `zuno-aap`,
   `zuno-auth`, `openshift-lightspeed`, `openshift-keda`,
   `openshift-jobset-operator`, `openshift-lws-operator`,
   `openshift-kueue-operator`, `policy-controller-operator`. A fallback that
   looked for the existing Subscription in the default namespace would find
   nothing and hard-fail exactly where it was meant to tolerate, so the
   namespace is passed explicitly by those roles. Caught by reading the
   probe's own output, not by the refactor.

5. **Homonyms across catalogs are different operators.**
   `community-operators` publishes `limitador-operator`, `dns-operator` and
   `authorino-operator` unrelated to Red Hat's. Comparison is therefore
   `package@catalog` throughout, and repointing an orphaned Subscription at
   a same-named package is called out as a supply chain substitution.

## Verification

- P8 run live against `demo222`: 13 Subscriptions reported,
  `openshift-operators` correctly identified as the shared namespace,
  finding non-blocking.
- `ansible-playbook --syntax-check` on `day0_install`, `day1_install`,
  `day2_install`, `day0_check`, `day1_check`, `day3_check`.
- `make d1 check openshift-ai` and `make d3 check postgresql` green with the
  refactored roles in place.
- `python3 platform/docs/check_docs.py` PASS.

## Out of scope

Pinning `startingCSV` across the fleet (finding 3). Managing the
CatalogSource images themselves — this repository deliberately follows the
indexes the OCP version ships, and ADR-0558 records why pinning them was
rejected. Cleaning up the thirteen frozen Subscriptions on `demo222`: that
is an operator decision per operator, which is why P8 reports rather than
repairs.
