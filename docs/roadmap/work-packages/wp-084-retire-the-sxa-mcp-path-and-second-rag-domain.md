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

5. **Ten negative evaluation probes retargeted**, not deleted — deleting the
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

1. `oc -n zuno-data delete database.k8s.mariadb.com sxa` plus the matching
   `user`/`grant` CRs, then drop the `sxa` MariaDB database itself.
2. `oc -n zuno-data delete postgrescluster`-managed `rag-sxa` database/role
   (the retired `knowledge.sxa` index) — note PGO never recreates a dropped
   database, so confirm this is the intended, permanent removal first.
3. `vault kv delete zuno/sxa/mariadb-db` and `zuno/rag-sxa/postgresql-app`.
4. Re-apply the Keycloak realm: the `sales`/`adv` group descriptions no
   longer mention sales-db.

Then, once deployed:

5. Rebuild the rag-ingestion image and recompile the PipelineVersion
   (`make d2 build rag-ingestion`, then `make d2 install rag-ingestion`).
6. Trigger one on-demand `load-sxa-dump` run. **Expect a full re-embed of
   `rag-sxa-legacy`**: every `doc_id` changed with the URL scheme, and with
   `deleteOrphans`/`incremental` enabled the run deletes the old corpus and
   indexes the new one. One-time cost, not steady state.
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
- After the operator steps above land: flip this WP to `Done` and add a dated
  MEMORY.md bullet.

## Out of scope / deferred

- Any replacement for the deterministic commercial-query capability. Comage
  loses exact historical aggregation and Finage loses deterministic
  revenue/billing lookups; both are re-grounded on retrieval. Restoring an
  exact-figure path needs a live source and a new ADR — `sales.*` against a
  real Salesforce server is the only route ADR-0206 leaves open.
