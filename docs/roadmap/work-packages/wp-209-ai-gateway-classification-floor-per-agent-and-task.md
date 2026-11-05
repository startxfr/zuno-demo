# WP-209: ai-gateway classification floor per agent and task

- **State:** Not started
- **ADRs:** [ADR-0565](../../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md)
- **Depends on:** none
- **Related:** [ADR-0594](../../adr/0594-give-the-three-experiences-the-same-mcp-tools-behind-signed-classification-markers.md) (signed markers already raise a turn), [WP-187](wp-187-carry-the-source-classification-through-unifai-rag-results.md), [WP-191](wp-191-same-mcp-tools-in-the-three-experiences.md)
- **Target:** v0.15
- **Estimated files touched:** ~8: `platform/okf/generate_stack_config.py`, a new `gitops/charts/ai-gateway/files/classification-floors.generated.yaml` and its ConfigMap template, `components/ai-gateway/app/main.py` and a new floor module, their tests, the CI drift check

> Why: ADR-0565 clause 5 asks the ai-gateway to enforce a per-(agent, task) classification floor itself, so a caller cannot lower the level by sending a lower header. It is the one clause of ADR-0565 that has no code. The operator validation and bundle overrides (WP-150) and the per-chunk classification (WP-187) are done, and ADR-0594 raises the turn from signed markers, which covers clause 3 in practice.

## Goal

`effective = max(header, floor(agent, task))` in the ai-gateway, with the floors generated from the admitted bundles, and an absent classification header treated as `C3` instead of `C1` once no current caller depends on the old default.

## Steps

1. **Inventory the callers that send no `X-Zuno-Data-Classification`.** Candidates named by the ADR: the mcp-gateway built-in tools and the acceptance gate. Add the three experiences (Open WebUI, OpenClaw, Dify) and kagent. The header defaults to `C1` today (`components/ai-gateway/app/main.py`, three handlers).
2. **Generate the floor slice.** Same pattern as `guardrails-modes.generated.yaml` and `model-routing.generated.yaml`: `platform/okf/generate_stack_config.py` writes it from the agents release, a ConfigMap mounts it, and a CI drift check fails when the file differs from the bundles.
3. **Enforce it in the gateway.** Compute the effective level from the header and the floor of the calling agent and task, as `local_only_for` is already ORed into the caller's local-only flag. Log a raised level.
4. **Change the default.** Treat an absent header as `C3` only after step 1 shows which callers must send a header; fix those callers first. A cluster with callers that cannot send one keeps `C1` until they do.
5. **Record the partial supersession.** ADR-0565 clause 3 (the session carries a monotone level) is covered in practice by ADR-0594's signed markers; say so in the ADR when this WP closes.

## Acceptance

- A request with a header lower than the agent's floor is routed and counted at the floor, with a unit test and a live probe through the gateway.
- Without a header, the request is treated as `C3` and no listed caller breaks (`make d3 test` and the three experiences' checks stay green).
- The drift check fails on a stale floor file.
