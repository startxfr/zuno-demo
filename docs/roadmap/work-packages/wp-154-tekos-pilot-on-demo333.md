# WP-154: tekos pilot on demo333

- **State:** Repo work in review
- **ADRs:** [ADR-0573](../../adr/0573-pilot-unifai-on-demo333-with-tekos-before-cutting-demo222-over.md), [ADR-0561](../../adr/0561-adopt-unifai-as-the-agent-platform.md)
- **Depends on:** [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md), [WP-147](wp-147-unifai-opentelemetry-instrumentation.md), [WP-148](wp-148-unifai-parity-memory-routing-quota-ux.md), [WP-149](wp-149-unifai-rag-qdrant-hybrid-sources-backup.md), [WP-150](wp-150-unifai-operator-okf-agent-bundles.md), [WP-151](wp-151-deploy-unifai-on-zuno-via-argocd.md), [WP-152](wp-152-mcp-gateway-evaluation-and-mcp-north-side.md), [WP-153](wp-153-guardrails-into-the-ai-gateway.md)
- **Related:** [ADR-0021](../../adr/0021-route-models-according-to-c1-c2-c3-classification.md), [ADR-0566](../../adr/0566-instrument-unifai-with-opentelemetry.md), [ADR-0568](../../adr/0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [WP-155](wp-155-migrate-remaining-agents-and-cut-demo222-over.md)
- **Target:** v0.11
- **Estimated files touched:** ~10 in `zuno-demo` — an UnifAI target in `evaluations/tekos/`, `gitops/charts/unifai/values.yaml` (tekos objects enabled), an evidence file under `docs/roadmap/evidence/`; fixes found during the pilot go to their own WP.

> The first end-to-end run of the whole stack, on one agent, on the cluster
> that is allowed to break. Nothing here touches demo222.

## Goal

tekos runs entirely on UnifAI on demo333 — signed OKF bundle, Confluence
corpus in Qdrant, web search and MCP tools, models through the ai-gateway —
and passes its existing evaluations plus the routing, classification, quota,
authorization, trace and restore checks below, side by side with the
agent-runtime tekos still deployed.

## Steps

**Live prerequisite.** demo333 is powered off: ask the user to power it on
before step 2. Pass `--context <demo333-context>` explicitly on every `oc`
command. demo333 also runs the `unifai-devel` and `unifai-olm` stacks; do not
modify them, and coordinate with the startx-unifai session before any
operator release. Never touch demo222.

1. **Offline: point the evaluations at UnifAI.** `evaluations/tekos/run_scenarios.py`
   and `security_checks.py` target agent-runtime (`RUNTIME_URL`) and the BFF.
   Add a `--target unifai` mode that drives the UnifAI chat/session API
   (MAS REST, as `fork/unifai-operator/internal/unifai/client.go` in
   startx-unifai calls it) with the same scenarios from
   `evaluations/tekos/scenarios.yaml`, so results are comparable. Do not
   fork the scenario file.

2. **Deploy tekos objects.** In `gitops/charts/unifai/values.yaml` enable
   the tekos `UnifaiAgentBundle` (OCI digest from `make d3 sign agents`,
   WP-150), the `UnifaiRAGSource` for the tekos Confluence space (WP-149),
   the `UnifaiProvider` for the MCP endpoint chosen in WP-152, and the
   `UnifaiLLM` pointing at the ai-gateway. Sync through the Ansible role
   (`make d1 install unifai` or the tier WP-151 set).

3. **Corpus.** Let the `UnifaiRAGSource` ingest the tekos Confluence corpus;
   watch GPU quota (it is already saturated) and run off-hours if needed.
   Run it a second time and confirm nothing is re-embedded.

4. **Evaluations.** Run `evaluations/tekos` scenarios and security checks
   with `--target unifai`, then the acceptance gate
   (`evaluations/tekos/run_acceptance_gate.py`). Record pass rates next to the
   agent-runtime baseline.

5. **Platform checks.** Each with its evidence (command + output):
   - routing/classification: for a C3 prompt `zuno_provider` is a local model
     only (C3 = local-only per ADR-0021), shown in the UnifAI UI badge (WP-148);
   - quota: exhaust a test quota and see a clean 429 in the UI;
   - MCP authz: a persona outside the tool's Keycloak group is refused;
   - RAG: a hybrid query returns sourced answers;
   - trace: one continuous trace UnifAI -> ai-gateway -> model in Tempo;
   - guardrails: detection counter in raw Prometheus (WP-153);
   - restore: Qdrant + Mongo restore drill from S3 into a scratch namespace
     (WP-149) returns the same hit count.

6. **Browser check.** Real persona login to the UnifAI UI through realm
   `zuno` with Playwright, as done for the zuno frontends; screenshot the
   tekos chat with the provider badge.

7. **Evidence.** Write the results to `docs/roadmap/evidence/` (follow the
   naming of existing files there) and list every defect found as a new WP
   or an open question here.

## Progress (2026-10-22, demo333)

Phase A (no GPU) and the first part of phase B (GPUs back) are done and measured:
see [the evidence file](../evidence/wp-154-tekos-pilot-phase-a.md).

- Step 1 (evaluations): `run_scenarios.py` and `security_checks.py` take
  `--target unifai` (`evaluations/tekos/unifai_target.py`).
- Step 2 (objects): the tekos bundle (throwaway signing key), a per-task MCP
  provider, a UnifAI team workspace, the retriever and two RAG sources
  (`tekos-satellite` 90 pages, `tekos-openshift` 411 pages, group ACLs) were deployed.
  The chart supports `okf.bundles[].teamId`, `retrievers` and `ragSources`.
- Steps 3-4: 16 / 17 scenarios (94%) against 16 / 20 for agent-runtime the same day,
  12 / 12 security checks, on a secured fork build held in demo333's internal registry.
- Defects found and fixed in the fork: team sessions without an acting user, the
  validator probing a forwarded-token LLM, RAG groups discarded in a team workspace,
  empty answer when the rounds run out; and in the operator the identity URL.
- Restore drill passed (step 5): `make d3 backup|check|restore unifai`; 501 Qdrant points
  and 18 MongoDB collections restored identical in a scratch namespace.
- Removed on 2026-10-22 at the user's request, to be redeployed later: the tekos
  test bundle and its objects, the retriever and the pilot team. The two RAG sources
  stay (ingested data).

Still to do: scenario 8 on warm local models,
the quota 429 and routing badge (WP-148 UI), the
guardrails counter (WP-153), the Playwright screenshot (step 6), and the real-key
bundle (waits for WP-158).

## Acceptance

All tekos scenarios and security checks pass on UnifAI at a rate not lower
than the agent-runtime baseline measured the same day; every check in step 5
has evidence; the Playwright login succeeds; `unifai-devel` and `unifai-olm`
are still Ready at the end.

## Open questions

- Does the UnifAI session API expose enough of the run (tool calls,
  retrieved sources) for `gate_checks.py`? If not, read it from OTel spans.
- Should the agent-runtime tekos be scaled down during the pilot to free
  CPU on demo333 (nodes already near full)? Ask the user.
