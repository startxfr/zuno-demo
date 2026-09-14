# WP-145: Fleet version and catalog policy

- **State:** Not started
- **ADRs:** [ADR-0559](../../adr/0559-follow-the-cluster-version-and-never-branch-by-ocp-version.md)
- **Depends on:** [WP-144](wp-144-olm-catalog-drop-tolerance.md)
- **Related:** [ADR-0048](../../adr/0048-discover-supported-operator-channels-and-serving-runtimes-at-deployment-time.md), [ADR-0558](../../adr/0558-tolerate-catalogs-that-stop-publishing-an-installed-operator.md), [WP-143](wp-143-mariadb-internal-external-pilot.md)
- **Target:** v0.9
- **Estimated files touched:** ~6 — a known-good version set under `platform/`, a chart for additional CatalogSources, `ansible/confidential.example.yml`, and the `check_docs.py` rule that validates the version set.

> Opened by ADR-0559, itself opened by a question from the team: should the
> repository be branched by OCP version? It should not. What remains is the
> mechanism that makes a single trunk safe across two OCP versions.

## Goal

One trunk must stay deployable on a Tech Preview cluster and a stable one at
the same time, with the divergence carried by cluster data, visible to the
readiness probes, and reproducible from a recorded version set.

## Steps

1. **Measure `demo333` at its next power-on — blocking, and free.** With
   `--context` passed explicitly: its ClusterVersion, its CatalogSource image
   tags, the packages its indexes serve cross-referenced against the eleven
   `demo222` lost, and whether any Subscription there has an empty `status`.
   This answers two questions at once: whether the `:v4.22` indexes still
   serve those packages, and whether the empty-status Subscriptions are a
   5.0-only symptom. Step 3 does not start until this is done.

2. **Record the known-good version set.** A data file under `platform/`,
   keyed by OCP version, listing the operator versions the platform is known
   to run on it. Validated by `platform/docs/check_docs.py`, on the model of
   the model-roles registry it already enforces. This is what makes a rebuild
   of a 4.22 cluster reproducible.

3. **Additional CatalogSources, only if step 1 justifies them.** A chart
   rendering CatalogSources pinned to an index that still serves the dropped
   packages, alongside the defaults and enabled per cluster. Every affected
   Subscription must name its `source`. Validate first on one operator with
   no stake, because OLM's behaviour with two indexes serving the same
   package at different versions has not been exercised here.

4. **Document the per-cluster pin keys** in `ansible/confidential.example.yml`,
   and state where `startingCSV` is set and why, per ADR-0559's last clause.

## Acceptance

The five Subscriptions with an empty `status` regain an `installedCSV`; the
three Applications stuck `Progressing` (`zuno-postgresql-d0`,
`zuno-connectivity-link-d0`, `zuno-rhtas-d0`) return to `Healthy`; and
`oc get installplan -A` shows no new unapproved plan. A restored path must
not become a travelled one.

## Open questions

- Do the `:v4.22` indexes still serve the eleven dropped packages? Unverified;
  `oc image info` on that index is unauthorized from the workstation. Step 1
  answers it.
- Is `demo333` actually still on OCP 4.22? Reported, not measured — the
  cluster is powered off.
- How does OLM resolve a package served by two indexes at different versions?
  Not exercised. Step 3 validates it on a low-stake operator first.
