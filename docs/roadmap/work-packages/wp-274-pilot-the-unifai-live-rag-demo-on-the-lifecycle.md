# WP-274: Pilot the UnifAI live RAG demo on the lifecycle

- **State:** Operator pending
- **ADRs:** [ADR-0616](../../adr/0616-prepare-and-play-every-catalogue-demo-through-one-make-demo-lifecycle.md)
- **Depends on:** [WP-271](wp-271-scaffold-every-demo-directory-and-the-catalogue-check.md)
- **Related:** [WP-273](wp-273-pilot-the-guardrails-demo-on-the-lifecycle.md) (the other pilot), [WP-200](wp-200-show-the-unifai-rag-working-live.md) (the live RAG first shown)
- **Target:** v0.16
- **Estimated files touched:** ~22: `docs/demo/unifai-live-rag.md`, `ansible/demos/unifai-live-rag/*`, `evaluations/unifai_rag_library.py` and its test, one evidence file

> Why: the second pilot covers what `guardrails` does not: a real `start` and `stop` that change shared state (a
> persona's documents), a demo with no golden-path probe, and an optional step that changes the cluster.

## Goal

`unifai-live-rag` is played end to end through `make demo` in both versions, with its documents prepared and removed
by `start` and `stop`, and its page rewritten to match.

## Steps

1. **Spike (1 hour, first):** prove that the UnifAI RAG endpoints answer through the UI route as a persona, with the
   sign-in of `evaluations/common/unifai_target.py` (`UnifaiTarget.client`): list documents
   (`/available.docs.get`), delete one (`/data.source.delete`), upload one (`/upload`), in the fork
   `startx-unifai` under `rag/infrastructure/http/docs.py` and `data_sources.py`. Note the path prefix of the UI route
   and the owner-403 trap. If the spike fails, `start` prints the manual upload and the owner decides at the gate.
2. Write `evaluations/unifai_rag_library.py` (`list`, `delete <names>`, `upload <files>`, `wait-done`), the password
   read at run time from the Secret the browser checks use, never printed, and a unit test with a fake HTTP server.
3. Page, by the owner's decision of 2026-11-14: `start` uploads the two demo files before the session, so the 5-minute
   row 0:30 is rewritten to show the loaded library and its **Done** state instead of a live upload. Replace
   `## Before you start` by `## Presenter lifecycle`:
   - `### Status`: the reads of the UnifaiStack, `docling-serve`, `unifai-rag-server`, `unifai-rag-celery`, `qdrant`,
     the `embeddings` InferenceService, the workflows and retrievers;
   - `### Check`: no golden-path probe; the same reads plus one retriever answer;
   - `### Install`: Nothing to do (shared platform, verified);
   - `### Start`: the two browser profiles (human), what the file did (library cleaned of the three named files,
     `travel-and-expense-policy.md` and `on-call-rota-handbook.md` uploaded for consultant-01 and **Done**, model
     warmed), never `questions.md`;
   - `### Stop`: what the file removes;
   - `### Uninstall`: Nothing to do.
   Appendix C (the optional Confluence resync) moves to the lifecycle text and the manifest: rows 9:30 and 12:45 are
   declared `mutating: true, optional: true, freeze: forbidden`; the step prints the commands and never runs them.
4. Files: `start.yml` and `stop.yml` call the library script as consultant-01 (and sale-01 for the 15-minute
   isolation rows), declared changing in `demo.yml`; `status.yml` and `check.yml` from the reads above.
5. **With the owner's named go** for the start and stop on demo333: `make demo use unifai-live-rag 15` and the whole
   sequence by hand, then `DEMO_CONFIRM=unifai-live-rag make demo rehearse unifai-live-rag 5` and `... 15`.
6. Write the evidence `docs/roadmap/evidence/wp-274-unifai-live-rag-rehearsal-2026-11-16.md`.

## Acceptance

- Both rehearsals end with `RESULT: PASS`; the optional rows show `SKIPPED (mutating)`.
- After `stop`, consultant-01's library holds none of the three named files.
- The owner reviews the evidence at the gate of 2026-11-16, 12:00, and gives or refuses the go for the rollout.
