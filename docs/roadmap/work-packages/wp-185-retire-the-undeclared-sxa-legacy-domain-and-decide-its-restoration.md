# WP-185: Retire the undeclared sxa-legacy domain, then decide whether to restore it

- **State:** Repo work merged (steps 2 and 3 are on zuno-demo-agents devel, `98a0cb9`, 2026-11-02, and ride in agents release 0.9.0; the release, its admission, and steps 1, 4, 5 and the gate remain)
- **ADRs:** [ADR-0219](../../adr/0219-serve-sxa-only-as-a-historical-rag-corpus.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md)
- **Depends on:** none
- **Related:** [WP-168](wp-168-migrate-the-red-hat-product-documentation-to-unifai-rag.md), [WP-155](wp-155-migrate-remaining-agents-and-cut-demo222-over.md), [WP-164](wp-164-generate-stack-configuration-from-the-corp-release.md)
- **Target:** v0.11
- **Estimated files touched:** ~4 agent bundles and 7 tasks in `zuno-demo-agents`; in `zuno-demo` the regenerated `platform/okf/stack-config.generated.yaml` and the corp release pin, ADR-0219 and ADR-0568 notes, `knowledge/sxa-legacy/domain.yaml` and `policies/data-classification/classification.yaml` depending on the decision; an evidence file.

> Found on 2026-11-02 while comparing an archive of leftover files with `origin/devel`. The archive held nothing
> unpublished: its files are byte-identical to the last commit before WP-156 and WP-168 removed the old RAG stack. The
> analysis found that the retirement dropped the `knowledge.sxa-legacy` content without a recorded decision. This brief
> first stops the harm (agents that declare a domain nothing serves), then asks the user whether the record is worth restoring.

## Goal

No agent bundle or task declares a knowledge domain that nothing serves, and the loss of the SXA record is either
reversed by a chosen, costed route or recorded as a decision.

## Context

- `knowledge.sxa-legacy` was the company's closed pre-2021 record, about 310,000 documents (319,841 rows in the
  `rag-sxa-legacy` database), loaded from an SQL dump in S3 by the `load-sxa-dump` adapter of `rag-ingestion`
  ([ADR-0219](../../adr/0219-serve-sxa-only-as-a-historical-rag-corpus.md): "the one surviving domain").
- Declared today by comage, cognos, advantage and finage (`platform/okf/stack-config.generated.yaml` lines 38, 85, 109,
  129, 207, 232, 248, 260) and by seven tasks in `zuno-demo-agents`, for example `agents/comage/tasks/compare-historical-deals.md`
  line 8 and `agents/finage/tasks/answer-finance-question.md`. Each declares it at C2 for the groups sales, board, adv, finance.
- Nothing serves it. No UnifAI source carries it (`docs/roadmap/evidence/wp-155-parity-wave1.md` line 216: "not ingested"),
  and the agents' retrievers query Confluence and Web sources with no domain filter. A question that needs the historical record
  gets no error and no empty marker: the model answers from unrelated pages or says it found nothing.
- [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md) required the UnifAI source
  types to "cover everything rag-ingestion fetches today before rag-ingestion is retired", including a `sql-dump` type for this dump.
  It was not built and the retirement went ahead. WP-168 lists the `rag-sxa-legacy` database among the dropped ones and says nothing
  about the content. No document accepts the loss.
- The data: the source dump `sxa.schema.sql` and `sxa.data.sql` was copied to `zuno-demo-sources/sxa-dump/`
  ([ADR-0546](../../adr/0546-introduce-a-cross-cluster-source-bucket-and-per-cluster-s3-bucket-convention.md) lines 62 and 127); it probably still exists, but no document
  confirms it. The Vault path `sxa-corpus/s3` was deleted. The pg_dump kept outside the repository for `rag-sxa-legacy` was a few KB, so the
  embedded rows were not preserved. Re-embedding about 310,000 documents is untimed; the GPU quota is a risk.

## Steps

1. **Live exposure.** List every bundle, task and ceiling that names the domain. On demo333, ask one real question per affected agent
   (as a persona holding the group) and record what comes back.
2. **Remove the declarations** in `zuno-demo-agents`: the four agent bundles and seven tasks. Release and promote through the usual chain
   (the user merges the pull request, then the release workflows and `make d3 admit agents`, run by the session that owns admissions).
3. **Regenerate** in `zuno-demo`: the stack configuration and the other generated files from the new corp release. Touch
   `classification.yaml` and `knowledge/sxa-legacy/domain.yaml` only as far as the decision of step 6 allows.
4. **ADR notes.** Dated notes in ADR-0219 and ADR-0568: the domain is not served, why, and the state of the `sql-dump` precondition.
   No new ADR.
5. **Verify the data.** Without changing anything, check that the dump objects still exist in the source bucket and note who can read them.
   Re-creating read access (Vault, IAM) needs the user's go.
6. **Decision gate (user).** Does the SXA record matter for the demo? The brief carries this table, filled in with the findings of step 5:

   | Route | Work | Keeps | Cost and risk |
   |---|---|---|---|
   | Rebuild `sql-dump` in the fork | a connector, an operator field, chart wiring, tests, an S3 secret (4 to 6 files); reuse `_fetch_sxa_dump_bytes`, `_split_sql_statements`, `_load_sxa_dump` and the SQL parsers of `rag_ingestion.py` lines 1080 to 1490 at `877d8c83^` | change detection, one source of truth, the route ADR-0568 planned | most work, depends on fork and operator releases, full re-embed, GPU quota |
   | Convert to uploaded documents | one Job that renders each row and uploads in batches with `visibility` and `aclGroups` | no fork change | no incremental sync, upload capacity of the API unverified, a one-off tool |
   | Leave it dropped | nothing | the cleanup of steps 1 to 4 | agents lose their historical lookups; ADR-0219's intent is reversed |

7. **Follow-up.** If the user chooses a restoration route, open a work package for it. If the user chooses to drop the domain, mark it dropped in
   both ADRs and remove the descriptor and the classification entry.

## Acceptance

- No deployed bundle declares `knowledge.sxa-legacy`; the stack configuration is regenerated from the new release.
- A historical-deals question to comage no longer falls back silently: the task is removed, or the agent states the domain is unavailable.
- The ADR notes and the user's decision on restoration are on `devel`; a restoration WP exists if the answer was yes.

## Decisions

- **2026-11-02 (user):** clean up first, decide on restoration after, and open no fork work until the user says yes.
- **2026-11-02 (user):** the cleanup ships in agents release 0.9.0 with the experience clients, not after it.
- **2026-11-02 (user):** the two tasks whose only knowledge source is the domain are removed, not kept with a notice: comage `compare-historical-deals` (the one served agent)
  and cognos `review-historical-commercial-data`. All four agents are cleaned now, although advantage, cognos and finage are placeholders that no bundle serves.
- **2026-11-02 (user):** finage's two invoice tasks stay, without the domain and with their text rewritten, because they are the only `project_required: true` tasks of the
  repository (the exemplars of ADR-0512).
- Versions chosen for the branch: comage, cognos, advantage and finage go from 0.1.0 to 0.2.0. These agents are 0.x and unverified, so a breaking change bumps the
  minor; RELEASING.md says "major" for a removed task, and a jump to 1.0.0 would mislabel agents that are not stable. The repository `VERSION` is left for the release.
