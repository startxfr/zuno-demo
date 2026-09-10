# WP-143: MariaDB internal/external mode pilot

- **State:** Not started
- **ADRs:** [ADR-0352](../../adr/0352-run-day-0-platform-services-in-internal-or-external-mode.md)
- **Depends on:** none
- **Related:** [ADR-0345](../../adr/0345-make-self-generated-vault-credentials-idempotent.md), [ADR-0547](../../adr/0547-parameterize-every-cluster-specific-value-in-ansible.md)
- **Target:** v0.9
- **Estimated files touched:** ~10 — `ansible/roles/mariadb/tasks/{install,precheck,uninstall}.yml`, `ansible/confidential.example.yml`, a new `ansible/tasks/resolve_mariadb_endpoint.yml`, `ansible/roles/{rag_ingestion,mlops,rhtas}/tasks/install.yml` (host/username injection), `gitops/charts/{rag-ingestion,mlops,rhtas}` values seams, the mariadb role README.

> Execute this brief as a standalone task from the repository root. It is
> ADR-0352's clause-9 pilot: the first component to implement the
> internal/external mode contract, chosen because its consumers already
> resolve their credentials from Vault independently of the mariadb chart.
> Every ADR-0352 vocabulary decision (key names, gating semantics, check
> assertions) is reused verbatim — this WP invents no second vocabulary.

## Goal

`zuno_mariadb_mode: internal | external` works end to end. Internal mode
(default, key absent) is bit-for-bit today's behavior. External mode: the
built-in MariaDB is not deployed; the role validates the
`zuno_mariadb_external_*` payload, asserts the endpoint, seeds the three
per-database credential pairs into Vault, and the three consumers
(rag-ingestion, mlops, rhtas/Trillian) run unchanged against the external
endpoint — proven live on `demo333` with a simulated external instance and
a full data migration there and back.

## Why MariaDB pilots (ADR-0352 clause 9)

The three consumer Secrets (`rag-pipeline-db` in `zuno-ai-build`,
`mlops-dspa-mysql-credentials` in `zuno-mlops`, `rhtas-trillian-db` in
`zuno-rhtas`) are each created by the consumer's own chart from Vault
(`rag/pipeline-db`, `mlops/dspa-mysql`, `rhtas/trillian-mysql`) — the
credential plumbing is already mode-agnostic. Two real gaps remain and are
this WP's substance: the endpoint **hosts are chart literals** in all three
consumer charts (an ADR-0547/ADR-0352-clause-5 violation), and the rhtas
role loads the Trillian schema by **`k8s_exec` into pod `mariadb-0`**
(`ansible/roles/rhtas/tasks/install.yml:110-150`), which cannot exist in
external mode.

## Repo changes

1. **`ansible/confidential.example.yml`** — the ADR-0352 clause-2 mariadb
   block: `zuno_mariadb_mode` (absent = internal),
   `zuno_mariadb_external_host`, `_port` (`"3306"`), `_ca_bundle` (`""`),
   and `zuno_mariadb_external_db_{mlpipeline,mlops,trillian}_{username,password}`.
   Consequences-when-unset documented per the B8 precedent (ADR-0547).
   External usernames default to today's static names; a different
   username flows the Helm-values path (non-secret), the password flows
   only confidential.yml → Vault → ExternalSecret.

2. **`ansible/roles/mariadb/tasks/install.yml`** — hoist
   `load_cluster_vars.yml` + the confidential.yml stat/include_vars pair
   to the top (today they sit *after* the `-d0` apply); set
   `_mariadb_mode` (default `internal`); gate the entire internal
   sequence (PackageManifest discovery → `-d0` → `-d1` → waits →
   `appProtocol` patch) on internal mode. External branch, in order:
   fail-fast on any required key left at the `"xxxxxx"` sentinel; TCP
   reachability assertion on host:port; seed the three credential pairs
   plus root-equivalent nothing (external root is not ours) into the
   existing Vault paths via direct `vault kv put` with `no_log` (the
   `zuno/mariadb/s3` precedent — real external credentials re-apply, they
   are not create-if-missing); AUTH assertion per database via a
   short-lived mysql-client Job. Reconcile needs no work: mariadb has no
   `reconcile.yml`, so `day1_reconcile.yml` falls back to this gated
   install.

3. **`ansible/roles/mariadb/tasks/precheck.yml`** — add the same load
   pair + gate (the smtp-asymmetry fix ADR-0352 clause 4 mandates).
   External personality: endpoint reachability + per-database AUTH,
   never Application Synced/Healthy or `MariaDB/mariadb` CR readiness.
   `record_state.yml` semantics unchanged (record-state, never fail).

4. **`ansible/roles/mariadb/tasks/uninstall.yml`** — gated: strict no-op
   in external mode (the platform never deletes a service it does not
   own).

5. **`ansible/tasks/resolve_mariadb_endpoint.yml`** (new) — sets
   `mariadb_endpoint_host`/`mariadb_endpoint_port` and the per-database
   usernames from the mode + payload, defaulting to
   `mariadb.zuno-data.svc.cluster.local`/`3306` and the static names.
   Consumers consume these facts, **never `zuno_mariadb_mode`**
   (ADR-0352 clause 11).

6. **Consumer host/username injection** — `rag_ingestion`, `mlops` and
   `rhtas` roles include the resolver and inject
   host/port/username into their charts via
   `gitops_app_extra_helm_values`, composing the **complete** values
   document (the wholesale-replacement trap — model:
   `ansible/roles/rhtas/tasks/install.yml`'s existing comment). Chart
   defaults keep the current literals so a plain render is byte-identical
   (inertia proof per ADR-0547 clause 4, with the Applications' own
   toggles ON).

7. **rhtas Trillian schema load** — replace the `k8s_cp` + `k8s_exec`
   into `mariadb-0` with a short-lived SQL client Job targeting
   `mariadb_endpoint_host`, mode-agnostic (works identically internal
   and external).

8. **`ansible/roles/mariadb/README.md`** — external-mode runbook +
   honest feature-parity note: metrics (mysqld-exporter, ServiceMonitor,
   `networkpolicy-metrics.yaml`), the `vault-issuer-mariadb`
   ClusterIssuer and S3 physical backups are internal-only and do not
   apply; the `mysql_*` Grafana/Perses series lose their source.

## What NOT to touch

- `demo222` — anything (branch, cluster, S3, Route53).
- PostgreSQL, Keycloak, or any other ADR-0352 component: this pilot is
  mariadb only; the next components land in their own WPs.
- The mariadb chart's internal operand templates (`mariadb.yaml`,
  `database-*.yaml`, ExternalSecrets): external mode skips both
  Applications entirely; no chart-level `mode` key is introduced — the
  Ansible role is the gate, per ADR-0352 clause 4.
- TLS to the external endpoint (`zuno_mariadb_external_ca_bundle` is
  accepted and stored but not yet wired into the DSPA/ODH trust bundle)
  — recorded below as deferred.

## Tests / verification checklist

1. Inertia proof (internal): `helm template` of rag-ingestion, mlops and
   rhtas with their Applications' toggles ON, before vs after —
   byte-identical; `make d1 check` + `make d2 check` green with no
   confidential.yml mariadb keys present.
2. Sentinel validation: `zuno_mariadb_mode: external` with a missing key
   fails fast in the role, before any apply, naming the key.
3. External check personality: with mode external, `make d1 check
   mariadb` asserts reachability + per-DB auth and never inspects the
   `zuno-mariadb-*` Applications.
4. Uninstall no-op: with mode external, `make d1 uninstall mariadb`
   deletes nothing on the external instance.
5. `python3 platform/docs/check_docs.py` passes after every docs edit.

## Live verification (demo333)

Data reality: the three databases are not disposable — `trillian` holds
the RHTAS transparency log (losing it breaks signature inclusion proofs
and the ADR-0549 ledger), `mlpipeline`/`mlops` hold DSPA pipeline
metadata. The rehearsal is therefore a **full migration there and back**,
with operator confirmation before each destructive step:

1. Simulated external endpoint: a dedicated namespace (not managed by any
   Application), a minimal MariaDB StatefulSet + Service + Secret applied
   from one-shot manifests kept out of the repo charts — it simulates a
   service the platform does not own. Create the three databases + users
   (the "external DBA" role).
2. Migration out: `mysqldump` of the three databases from `mariadb-0`,
   import into the simulated instance, row counts compared.
3. ✋ `make d1 uninstall mariadb`; flip the workstation's
   `ansible/confidential.yml` to `external` + endpoint + credentials.
4. `make d1 install mariadb` (external assertions pass); re-run the
   consumer roles; proofs: both DSPAs Ready against the new endpoint,
   `make d2 check supply-chain` green (Trillian log intact = the
   migration proof), `make d1 check` green.
5. Migration back: dump from the simulated instance → ✋ flip `internal`
   → internal reinstall → import → consumer re-runs → full `make d1
   check` + `make d2 check` green → simulated namespace deleted.
6. ADR-0352 moves to `Partially implemented` with a dated clause-9
   progress note; tracker/index/version tables recomputed.

## Status updates (then re-run check_docs.py)

- **2026-09-10 — Not started.** Brief authored (ADR-0352 clause 9).

## Out of scope / deferred

- External-endpoint TLS: `_external_ca_bundle` plumbing into the
  DSPA/ODH trust bundles (`dsp-mlflow-trust-rag-dspa` and the mlops
  equivalent, ADR-0545/WP-129 ownership) — a follow-up once a real
  TLS-fronted external MariaDB exists.
- Every other ADR-0352 component (keycloak is next per clause 9).
- Data-migration automation: the dump/import here is a rehearsal
  procedure, not a shipped tool (ADR-0352 clause 4: flips are migration
  events, out of scope).

## Completion criteria

- All eight repo changes landed with the clause-4 symmetric gating and
  the inertia proof recorded.
- The live rehearsal above completed on `demo333`, ending at nominal
  internal state with all checks green.
- ADR-0352 `Partially implemented`, this brief `Done`, tracker + by-version
  table + `versions.md` + ADR index consistent, `check_docs.py` PASS.
