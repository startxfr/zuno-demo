# WP-084: Retire the SXA MCP/SQL path and the second RAG domain (promotes ADR-0219)

- **State:** Repo work merged (2026-08-26). Operator teardown and one re-ingestion still open — see below.
- **ADRs:** ADR-0219 (Implemented); supersedes ADR-0216 and ADR-0217 in full
- **Supersedes:** [WP-065](wp-065-sxa-mariadb-import-rag.md) and [WP-067](wp-067-sxa-weekly-rag-corpus.md), both Abandoned
- **Depends on:** WP-065, WP-067 (both merged; this WP removes what they built)
- **Estimated files touched:** ~150

> Execute this brief as a standalone task from the repository root.

## Goal

Serve SXA — the company's commercial record from before 2021 — through RAG
only. No live SQL content, no MCP tool surface, one knowledge domain.

## What changed

1. **ADR-0219 authored**, superseding ADR-0216 and ADR-0217. Both are renamed
   and rewritten to drop "anonymized" from filenames, titles and bodies:
   `sxa_anonymize.py` was deleted on 2026-08-23 and no path has anonymized SXA
   content since, so the language asserted a property the code does not have.
   A deliberate exception to the ADR-immutability convention, recorded as such.
   ADR-0016 becomes superseded in full.

2. **`knowledge.sxa-legacy` is the single domain.** `allowed_groups` widens to
   `[sales, board, adv, finance]` — the union of what it and the retired
   `knowledge.sxa` granted, so no agent loses reach. This amends ADR-0340's
   access-intent row and retires WP-35's "Advantage denied sxa-legacy"
   negative test; the boundary that still holds is `knowledge.sales`.

3. **`load-sxa-dump` drops MariaDB**, parsing the S3 schema/data pair in pure
   Python via ADR-0217's parser. Record URLs move from `sxa-mariadb://` to
   `sxa-dump://`, matching the domain descriptor for the first time.

4. **Deleted:** the five `sxa.*` capabilities and their bindings; the
   `sales-db` MCP server, chart and Applications; the `sql-schema` Day-2 run
   component and `ansible/roles/sql_schema`; `data/sxa/`; the MariaDB `sxa`
   database and its Vault seed; `knowledge.sxa`, `fetch-sxa`, the `rag-sxa`
   pgvector database.

5. **Ingestion throughput fixed so the re-ingestion is possible at all**
   (commit `3258a1f`). `load-sxa-dump` renders one document per table row —
   314,428 of them, measured live. `normalize`, `chunk`, `embed` and
   `index-pgvector` were strictly serial: `normalize` clocked 747 docs/min,
   the full run projected past 30h, and no attempt had ever survived past
   6h28. `embed` batched only *within* a record, so on a corpus of
   single-chunk documents `EMBEDDING_BATCH_SIZE` was inert. The three
   S3-bound stages now use the pool idiom `detect-changes` already had,
   `embed` pools chunks across documents, and `index-pgvector` commits per
   window. Four knobs (`NORMALIZE_CONCURRENCY`, `CHUNK_CONCURRENCY`,
   `EMBED_CONCURRENCY`, `INDEX_READ_CONCURRENCY`) are wired through
   values.yaml, both ConfigMap templates and `CONFIG_KEYS`.

6. **Ten negative evaluation probes retargeted**, not deleted — deleting the
   bindings turns an unbound name into a 404, not the 403 they assert.
   ADR-0037's mandatory gateway-bypass test moves from `sales-db-mcp` to
   `confluence-mcp`, which carries the identical NetworkPolicy and gateway
   token check.

## What NOT to touch

- The shared MariaDB instance, its `DestinationRule` and the
  `excludeInboundPorts: "3306"` mesh fix — they serve Kubeflow Pipelines
  metadata, not SXA.
- `_split_sql_statements` and the `sqlparse` dependency — the surviving
  parser calls it.
- The `sales.*` capability namespace — still deliberately vacant, reserved
  for a future live-Salesforce server (ADR-0206).
- `platform/supply-chain/pinned-releases.yaml` and
  `release-v0.1.0-manifest.yaml` — append-only audit ledgers, left as
  historical record.

## Acceptance checks (run from repo root; all must pass)

```
python3 platform/docs/check_docs.py
python3 platform/docs/check_knowledge_refs.py
python3 platform/supply-chain/validate_okf_bundle.py
python3 platform/supply-chain/check_mcp_server_conformance.py     # 3 servers
python3 platform/supply-chain/check_build_matrix.py
python3 platform/okf/generate_authorization_matrix.py --check --all
python3 platform/okf/run_agent_contract_tests.py
python3 operator/aiagent-operator/validate_contract.py
python3 evaluations/tekos/gate_checks.py
(cd components/rag-ingestion && .venv/bin/python tests/test_source_adapters.py)
(cd components/mcp-gateway  && .venv/bin/python tests/test_bindings.py)
(cd components/agent-runtime && python3 tests/test_registry.py)
for c in gitops/charts/*/; do helm lint "$c"; done
for p in ansible/playbooks/*.yml; do ansible-playbook -i ansible/inventories/demo/hosts.yml "$p" --syntax-check; done
```

## Operator / human follow-up (not executable by the model)

**Run the teardown BEFORE deploying these commits to an existing cluster.**
`make d2 uninstall mcp` now carries retired-resource cleanup tasks that
reclaim the sales-db Applications, the `zuno-sxa-schema` ConfigMap and the
`sql-schema-postgresql-credentials` ExternalSecret. What it does *not* cover,
because their charts are gone:

1. ~~Delete the `sxa` MariaDB `Database`/`User`/`Grant` CRs and the database
   itself.~~ **Verified 2026-08-26 — nothing to do on this cluster.** No
   `sxa` MariaDB CR exists in any namespace, and MariaDB holds only `mlops`
   and `mlpipeline`; the `sxa` database and user were never provisioned here.
   The same is true of the `sales-db` ArgoCD Applications, the
   `zuno-sxa-schema` ConfigMap and the `sql-schema` ExternalSecret — all
   already absent, so the `make d2 uninstall mcp` retired-resource cleanup is
   a no-op here. Both are kept for clusters that *did* provision them.

2. ~~Drop the stranded `rag-sxa` database and `ragsxa` role.~~ **DONE
   2026-08-26.** Pre-flight confirmed it was safe to remove: 8438 kB with
   `document_embeddings` at 0 rows, 0 active connections, the role owned no
   databases and held no memberships, and `postgrescluster.spec.users` no
   longer listed `ragsxa` — PGO had already let go of it and would never
   reclaim it.

   ```
   oc -n zuno-data exec zuno-postgresql-instance1-vb9g-0 -c database -- \
     psql -U postgres -c 'DROP DATABASE "rag-sxa";' -c 'DROP ROLE ragsxa;'
   ```

   Verified after: `pg_database` holds `rag-adv`, `rag-project`, `rag-sales`,
   `rag-sxa-legacy`, `rag-tech`; the only remaining sxa role is
   `ragsxalegacy`; all four `sxa-legacy` secrets intact. PGO reconcile stayed
   healthy — `wrote PostgreSQL users` with empty stderr, no error loop, which
   is the specific failure mode a *declared-but-missing* database causes.
   `rag-sxa-legacy` was left untouched.

3. ~~`vault kv delete zuno/sxa/mariadb-db` and
   `zuno/rag-sxa/postgresql-app`.~~ **DONE 2026-08-26.** Both prefixes held
   exactly one secret each and nothing else, so removing them stranded
   nothing. Verified before and after that the two neighbours which must
   survive were untouched: `zuno/sxa-corpus/s3` (the dump's S3 credentials,
   still consumed by `load-sxa-dump`) and `zuno/rag-sxa-legacy/postgresql-app`
   (the surviving domain). Afterwards `zuno/sxa` and `zuno/rag-sxa` list
   empty.

   Executed as `vault kv metadata delete`, **not** the `vault kv delete` this
   step originally specified. On KV v2 a plain `kv delete` only writes a
   deletion marker and leaves the prior version recoverable - for credentials
   to databases that no longer exist, leaving a recoverable copy is the wrong
   outcome. `metadata delete` removes every version permanently, so this is
   irreversible by design rather than by accident.

4. ~~Re-apply the Keycloak realm.~~ **DONE 2026-08-26.** `KeycloakRealmImport`
   is create-only — it has no update path for an already-existing group's
   attributes, so the `de1524e` repo edit alone would never have reached the
   live realm via ArgoCD sync. Patched both group descriptions directly via
   the Keycloak admin REST API instead. Verified live just now: `GET
   /admin/realms/zuno/groups/{sales,adv}` both return the "grants web-search
   tool rights" wording with no mention of sales-db.

Then, once deployed:

5. ~~Rebuild the rag-ingestion image and recompile the PipelineVersion~~
   **DONE 2026-08-26**: `make d2 build rag-ingestion` produced Build
   `rag-ingestion-13` from `de1524e` (signed,
   `rag-ingestion@sha256:c2426f4f…`), and `make d2 install rag-ingestion`
   applied PipelineVersions `v0-5-0` / `v0-5-0-sxa-legacy`. Both plays ended
   `failed=0`. Verified live: `CONFIG_KEYS` requires 44 keys and both
   `rag-ingestion-config` and `rag-ingestion-config-sxa-legacy` carry all 44
   (`missing=NONE`) — a key in `CONFIG_KEYS` absent from any domain's
   ConfigMap is a `CreateContainerConfigError` at pod start. The
   recurring-run reconciler touched `knowledge.tech` only; `sxa-legacy` is
   correctly unscheduled per decision 2.
6. Trigger one on-demand `load-sxa-dump` run — **still open**.

   An earlier revision of this step said to delete
   `manifests-sxa-legacy/manifest.json` first, on the theory that the stale
   manifest would make `detect-changes` report zero changes against an empty
   index and "succeed" having written nothing. **That does not apply to this
   run.** `detect-changes` classifies by doc_id membership
   (`new_ids = [d for d in current if d not in manifest]`), and
   `doc_id_for()` is `sha256(url)[:32]`. Because decision 3 moved every record
   URL from `sxa-mariadb://` to `sxa-dump://`, not one new doc_id can collide
   with a stale manifest entry: the run classifies all 310,537 records as
   **new** and every old manifest entry as **deleted**. A leftover manifest is
   therefore inert here, and deleting it changes nothing. The zero-delta trap
   is real, but only for a re-run where the URL scheme has *not* changed —
   which is every future run of this domain. `rag-sxa-legacy` holds 0 rows today (verified
   2026-08-26). This is therefore a **first full index of 314,428
   documents, not a re-embed** — the URL-scheme change from `sxa-mariadb://`
   to `sxa-dump://` did rewrite every `doc_id`, but with the index empty
   `deleteOrphans` has nothing to delete. The cost is the initial ingestion
   and the throughput fix in item 5 is what makes it survivable.

   **First attempt (`e62e61cb`, triggered 14:20) hit a second throughput bug
   and was terminated 16:51, still on `detect-changes`.** `load-sxa-dump`
   completed cleanly (310,537 raw docs, ~37 min). `detect-changes` then
   pegged one core at 100% for over 2h with no completion in sight —
   confirmed via `ps` inside the pod, not a hang, genuinely CPU-bound.
   Root cause: `unchanged_ids = [d for d in current if d not in new_ids and
   d not in changed_ids]` tested list membership against `new_ids`
   (~310k long here, since this is a first full index — see above) inside a
   loop over all 310k current docs — O(n²), tens of billions of comparisons.
   Item 5's throughput fix covered `normalize`/`chunk`/`embed`/
   `index-pgvector`; this stage was untouched because it was already fast at
   every previously-tested corpus size. Fixed in `d340e7a` (set union instead
   of list membership); pushed. **Needs a rebuild (item 5 must be re-run
   against `d340e7a`) and a fresh trigger — the terminated run produced no
   usable output.**
6b. ~~Rebuild and redeploy `mcp-gateway`, `agent-runtime` and `rag-service`.~~
   **DONE 2026-08-26.** `make d2 build mcp|rag|agent`, all three `failed=0`,
   every image from `Git@ef21189` (= `origin/main`; the only unpushed commits
   were docs, so no push was needed). Verified *inside the running pods*:
   `mcp-gateway` carries 26 bound capabilities and **zero** `sxa.*` bindings
   (the one remaining `sxa.` in `tool-policy.yaml` is a comment citing this
   ADR); `mcp-gateway` and `agent-runtime` both resolve
   `knowledge.sxa-legacy` to `['sales','board','adv','finance']` with
   `knowledge.sxa` **ABSENT**; `rag-service` retains only the
   `knowledge.sxa-legacy` binding.

   **Hazard for any future `make d2 build agent`.** The role builds the image
   *first*, the ImageStream trigger immediately rolls a new pod, and the OKF
   re-signing Job runs **last**. The pod verifies bundles against the
   `agent-runtime-okf-signatures` ExternalSecret, whose `refreshInterval` is
   **1h** — so the new pod starts against signatures that predate the re-sign
   and dies with `failed to load OKF bundles: ... invalid signature when
   validating ASN.1 encoded signature` for all 8 agents. Seen here: the pod
   hit `CrashLoopBackOff` (6 restarts) while the previous pod kept serving.
   Recovery is to force the secret and restart:

   ```
   oc -n zuno-ai-run annotate externalsecret agent-runtime-okf-signatures \
     force-sync="$(date +%s)" --overwrite
   oc -n zuno-ai-run delete pod -l app=agent-runtime
   ```

   Left as an operational note rather than a code fix: reordering the role so
   signing precedes the build, or shortening the refresh interval, is a
   separate change and needs its own ADR discussion.

   Original finding, kept for the record: **the policy plane was never
   redeployed.** All three
   bake the policy/binding files into their images rather than mounting them
   (`components/mcp-gateway/Dockerfile:40,44` copies `policies` and
   `platform/bindings`; `agent-runtime/Dockerfile:50` copies
   `policies/knowledge`; `rag-service/Dockerfile:35` copies
   `platform/bindings/knowledge`). Step 5 rebuilt only rag-ingestion, so
   ADR-0219's policy plane is **not live**. Verified inside the running pods:

   - `mcp-gateway` still binds all five `sxa.*` capabilities (32 capabilities
     against the repo's 27) and its `tool-policy.yaml` still carries 10 `sxa.`
     references.
   - `agent-runtime` and `mcp-gateway` both still resolve
     `knowledge.sxa-legacy` to `[sales, board]` — **not** the widened
     `[sales, board, adv, finance]` — and still carry a live `knowledge.sxa`
     domain.
   - `rag-service` still declares `knowledge.sxa` bound to database `rag-sxa`,
     which step 2 dropped.

   The deployed state is internally *consistent* (bindings and policy are both
   pre-ADR-0219), so nothing is half-broken today — but step 7 would deny
   `adv` and `finance` on `knowledge.sxa-legacy` and look like a policy bug
   when it is only staleness.

   The dangling `rag-service` → `rag-sxa` binding is benign and self-resolving:
   `connect_all()` "never raises - a domain with no live pool is simply absent
   from `get_pool()`'s results (fail closed at query time, not startup time)".
   The domain lands in `_pool_errors` and is retried at most once per 15s, so
   the cost until the rebuild is log noise, not a crashloop.

7. Live-verify retrieval by role: Comage/Cognos/Advantage/Finage each reach
   `knowledge.sxa-legacy`; a caller in none of `[sales, board, adv, finance]`
   is denied.
8. Re-run the acceptance gates for the six agents whose scenarios changed
   (tekos, arkos, comage, advantage, finage, naveo) and confirm the
   retargeted probes still return 403, not 404.

## Status updates

- 2026-08-26: repo work merged across six commits. ADR-0219 `Implemented`,
  index row `Implemented`, ADR-0216/0217 `Superseded by ADR-0219`, ADR-0016
  `Superseded by ADR-0219`, WP-065/WP-067 `Abandoned`.
- 2026-08-26: operator step 5 executed (build + install, both `failed=0`);
  the CONFIG_KEYS/ConfigMap contract verified live at 44/44 on both domains.
  Steps 1-4 and 6-8 remain open — nothing has been ingested yet, so the
  throughput fix is deployed but unproven end-to-end.
- 2026-08-26: operator steps 1-4 re-scoped against the live cluster. Step 1
  is a no-op (MariaDB never held `sxa`); step 2 is the only real deletion and
  the database it removes is empty; step 4's repo prerequisite was missing and
  landed in `de1524e`.
- 2026-08-26: step 3 executed (both Vault seeds purged with `kv metadata
  delete`; `sxa-corpus/s3` and `rag-sxa-legacy/postgresql-app` verified
  intact). Steps 1-5 and 6b are now closed; only the step 6 run and the
  step 7/8 verification remain.
- 2026-08-26: step 6b executed and verified in-pod; the ADR-0219 policy plane
  is now live. Uncovered an ordering hazard in `agent_build` (image built and
  rolled before the OKF re-signing Job runs, against a 1h-refresh secret),
  documented inline above.
- 2026-08-26: the step 6 run `rag-corpus-ingestion-sxa-legacy-manual-wp084`
  was **terminated at 16:50:18Z**, not failed on its merits. Its
  `activeDeadlineSeconds` was `0` while both prior successful runs have the
  field unset, and the controller logged `Terminating pod which has exceeded
  workflow deadline` with the deadline equal to the run's own start time -
  Argo's terminate signature. `load-sxa-dump` had already written 310,537
  documents and its checksum, so a relaunch resumes at `detect-changes`. Owner
  of the termination unidentified; two peer sessions disclaimed it.
- 2026-08-26: static pre-check of step 8 - all 15 negative `403` tool probes
  across the six agents resolve to bound capabilities in the repo's
  `tool-bindings.yaml` (including the aliases `generate_image` ->
  `image.generation.create`, `read_gmail` -> `gmail.message.read`,
  `search_confluence` -> `confluence.page.search`), and no `sxa.*` capability
  remains. The 404-instead-of-403 risk is therefore cleared at the binding
  layer; the gates still need a live run once step 6b lands.
- 2026-08-26: step 2 executed - `rag-sxa` and `ragsxa` dropped, PGO reconcile
  verified healthy afterwards. Steps 3, 4 and 6-8 remain open; step 6 (the
  first full index of 314,428 documents) is the critical path.
- 2026-08-27: three more step-6 attempts failed, each on a different cause.
  `f5p8j` died overnight to a platform outage (Vault re-sealed on a pod
  restart, the mesh CA expired behind it, 77 pods down) - unrelated to this
  WP. `6cp5l` reached `index-pgvector` and wrote **249,911 of ~310,537 rows**
  before `psycopg.OperationalError: the connection is lost` at 12:50, one hour
  in. Progress survived: the per-window commits from item 5 plus the
  `ON CONFLICT (source, chunk_index)` upsert make a relaunch idempotent, so
  the remainder is ~60,600 documents upserting over the rest.
- 2026-08-27 (`788e8ea4`): `index-pgvector` now reconnects and replays.
  Holding one Postgres connection for a 3-5h stage cannot be assumed to
  survive; worse, the error handler's own `conn.rollback()` raised the same
  `OperationalError` and masked the original failure. The cursor moved inside
  the window loop, rollback/close are guarded, a fresh connection is opened
  with backoff and the window replayed, the S3 prefetch stays outside the
  retry, and the `finally` that rebuilds the ivfflat index uses the *current*
  connection so a dropped index is never left dropped on the error path.
- 2026-08-27 (`788e8ea4`): **a diagnosis recorded here as fact was wrong.**
  `detect-changes` had been raised to cpu:8/24Gi with a `values.yaml` comment
  asserting it was "latency-bound, not CPU-bound". The real cost was item 6's
  O(n^2), fixed in `d340e7ab`; the sizing was treating a symptom. It reverts
  to cpu:2/6Gi with the comment corrected. `readConcurrency: 64` stands.
  Because a `resources` block is part of the compiled spec, the
  PipelineVersion moves `v0-6-0` -> `v0-7-0`.
- 2026-08-27 (`253242b8`): `readConcurrency: 64` was doing less than claimed.
  `CorpusStore` hard-coded `max_pool_connections=32` - a number WP-58 picked
  to clear a *default* of 16, with a comment saying the pool must exceed the
  worker count. Raising the knob to 64 left it behind, and the live
  `detect-changes` pod logged a continuous `Connection pool is full,
  discarding connection` stream: half the workers re-establishing a TLS
  connection per GET, exactly the latency the knob exists to hide. The size is
  now derived from the widest knob (max, not sum - one stage per pod) plus
  headroom: 68 for this domain. Only a running pod's WARNING lines exposed
  this; no test or lint could have.
- 2026-08-27: step 6 attempt `9z45t` is **in flight**, launched 14:23Z by a
  peer session and left to run by the operator rather than restarted. Caveat
  for whoever reads its result: KFP runs one pod per stage, each pulling
  `rag-ingestion:latest` with `imagePullPolicy: Always`, so a rebuild swaps
  the image *between stages of the same run*. `9z45t` started `detect-changes`
  on the pre-fix image and its later stages take the rebuilt one - it is not
  evidence that any single build ran end-to-end. It also runs the `v0-6-0`
  spec, so `detect-changes` still has the oversized cpu:8/24Gi.
- 2026-08-27: **correction - the 12:50 failure was misattributed here and in
  `788e8ea4`'s message to restarting Postgres pods. It was not.** The pods'
  `RESTARTS` column is a per-container sum, not database crashes: every
  container of every instance shows exactly 2, including the init/sidecars,
  and all three nodes went `Ready` within 11s of each other at 08:35Z - a
  routine cluster restart. The `database` containers had been up continuously
  since 08:47Z, and Patroni logged nothing but "I am the leader with the lock"
  through the whole window, so there was no failover either. At 12:50 Postgres
  had been up four hours.

  The pgbouncer log has the real sequence: the pooled server connection hit
  pgbouncer's default 3600s `server_lifetime` (`closing because: server
  lifetime over (age=3611s)`), and the re-login immediately after failed with
  `password authentication failed for user "ragsxalegacy"`. With no server
  connection available, pgbouncer closed the client connection - which is the
  `the connection is lost` the stage saw. This was the only `server lifetime
  over` event of the day: every other client is recycled by the 600s idle
  timeout long before an hour, so this ingestion is the only workload that
  ever reaches it.

  Behind it, `.data.password` on `zuno-postgresql-pguser-ragsxalegacy` is
  claimed by two controllers - `postgrescluster-controller` (Apply, actively
  re-applying) and `externalsecrets.external-secrets.io` (`refreshInterval:
  1h`). **17 of 18 `pguser` secrets are in that state.** Investigating that
  conflict is explicitly out of scope for this WP (operator's decision,
  2026-08-27).

  **What this means for the retry in `788e8ea4`:** it recovers a transient
  drop, and nothing more. It cannot recover a stale credential, because the
  password is read from the environment once at pod start and the replay
  presents the same one. If a run dies here again with an auth failure in the
  pgbouncer log, the fix is not in `rag_ingestion.py`.
- Still open: compile `v0-7-0` (`make d2 install rag-ingestion`; verify the
  compiled object carries `cpu: 2`, never the play's exit code), then steps 7
  and 8.
- After the operator steps above land: flip this WP to `Done` and add a dated
  MEMORY.md bullet.

## Out of scope / deferred

- Any replacement for the deterministic commercial-query capability. Comage
  loses exact historical aggregation and Finage loses deterministic
  revenue/billing lookups; both are re-grounded on retrieval. Restoring an
  exact-figure path needs a live source and a new ADR — `sales.*` against a
  real Salesforce server is the only route ADR-0206 leaves open.
