# WP-168: the Red Hat product documentation on UnifAI, measured on demo333

Measured on `demo333` on 2026-10-23, operator 0.1.31, rag image `devel-ed9007147`
(fork `devel` with the `web` source, the `public` visibility and the fetch guard).

## Ingestion

- 38 `UnifaiRAGSource` of type `web`, visibility `public`, tags `knowledge.tech`,
  `product:<slug>`, `version:<n>`, generated from the rag-ingestion catalogue
  (`platform/knowledge/generate_redhat_web_sources.py`).
- All 38 pipelines ended `DONE`: 1079 pages (the catalogue had 874 documents; link
  discovery up to 50 per seed explains the difference). One run of about 35 minutes,
  one celery worker, the shared embeddings predictor.
- The operator reads the page count right after the trigger: long pipelines showed
  no count until their sources were reconciled again (a no-op annotation was enough).
  Not fixed.
- Finding: the celery workers did not consume `web_queue` (operator
  `CELERY_QUEUES`); worked around with `stack.extraEnv.ragCelery`, fixed in the
  operator (fork `devel` `1caaf4d24`, then `4cf41ba3e`, release 0.1.32).

## Comparison with rag-service

`evaluations/redhat-docs/compare.py`, 18 fixed questions, top 5, as `consultant-02`:
an expected book among the results.

| Engine | Questions answered |
|---|---|
| rag-service | 13 / 18 |
| UnifAI (`web` sources) | 16 / 18 |

UnifAI ranks the expected book first for 14 questions, rag-service for 11. Both miss the
OpenShift Virtualization template question (UnifAI answers with hosted control planes
pages); for the Quay mirroring question UnifAI answers with the OpenShift disconnected
environments books, which are relevant but not the expected Quay book. Scores differ in
nature (similarity versus rank fusion) and are not compared.

## Access rules

Searching `knowledge.tech` with the `WEB` and `CONFLUENCE` types, per persona:

| Persona | Groups | Web pages | Confluence pages |
|---|---|---|---|
| sale-01 | agent_comage, sales | 3 | 0 |
| finance-01 | agent_finage, finance | 3 | 0 |
| ai-ops-01 | agent_tekos | 3 | 3 |
| consultant-02 | consultant groups | 3 | 3 |

A caller outside the tekos and consultant groups finds the public pages and none of the
shared Confluence ones.

## Incremental sync

A source whose spec hash changed was registered again and synced: `2 pages (0 changed,
0 deleted)`, nothing re-embedded. A changed page alone, and a vanished page, are covered
by unit tests (`rag/tests/unit/test_web_source.py`); they were not replayed live.

## Left

mcp-gateway still merges `rag-service`; retiring `rag-service`, `rag-ingestion` and their
raw S3 prefix waits for the switch and the user's go.
