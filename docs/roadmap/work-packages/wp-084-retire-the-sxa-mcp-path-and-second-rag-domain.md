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

3. `vault kv delete zuno/sxa/mariadb-db` and `zuno/rag-sxa/postgresql-app`.
   Orphaned seeds: no ExternalSecret consumes either path any more, so they
   are inert rather than harmful, and this is housekeeping.

4. Re-apply the Keycloak realm. The repo edit this step assumed was already
   done was in fact missing until `de1524e` — the realm JSON still described
   the `sales`/`adv` groups as granting sales-db rights. The re-apply itself
   is still open.

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
6b. **Rebuild and redeploy `mcp-gateway`, `agent-runtime` and `rag-service`
   — discovered missing 2026-08-26, and it gates steps 7 and 8.** All three
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
- After the operator steps above land: flip this WP to `Done` and add a dated
  MEMORY.md bullet.

## Out of scope / deferred

- Any replacement for the deterministic commercial-query capability. Comage
  loses exact historical aggregation and Finage loses deterministic
  revenue/billing lookups; both are re-grounded on retrieval. Restoring an
  exact-figure path needs a live source and a new ADR — `sales.*` against a
  real Salesforce server is the only route ADR-0206 leaves open.
