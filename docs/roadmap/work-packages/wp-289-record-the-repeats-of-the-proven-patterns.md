# WP-289: Record the repeats of the proven patterns

- **State:** Not started
- **ADRs:** [ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
- **Depends on:** [WP-288](wp-288-record-the-first-batch-of-browser-demos.md)
- **Related:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md), [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md)
- **Target:** v0.16
- **Estimated files touched:** ~40: a cut list, a walkthrough or an allow list, and an evidence line per demo

> Why: ADR-0618 clause 14. After the first batch, the other demos repeat a pattern that is proven. The effort is about half a day each plus one scout and one take (the coder's estimate).

## Goal

All the scenarios that are not decided one by one have a published GIF.

## Steps

One demo at a time, each with a scout, a take, a review and the owner's named go:

- **Browser:** `dify`, `guardrails`, `unifai-agents`, `observability-trace`, `ai-gateway-routing`, `mcp-tools-by-group`, `lightspeed`, `aap-audited-operations`, `model-catalog-registry`. Two of them need a second persona's context (`unifai-agents`, `observability-trace`). `dify` leaves a run log that cannot be deleted: stated in its guard summary.
- **Terminal:** `gitops-day0-3`, `image-signing-admission`, `external-models`, `ai-gateway-sovereignty` (a cut list and its `record: {allow: [...]}` entries each; the long `make` outputs show their last lines through the cut).
- **Mixed:** `okf-signed-agent-release` (a terminal and one still of the repository's rendered file, not a call to a public site), `service-mesh-kiali` (a terminal and the Kiali overview).
- **Stills:** `quotas`, `lora-pipeline-mlflow-kueue`, `evaluation-trustyai-evalhub` (Grafana panels, runs that already finished, and repository files; nothing created, and no refused answer is provoked).

Rows that the page claims and the screen cannot show are settled before the take of their demo.

## Acceptance

- Each demo has a published GIF inside the limits of ADR-0617, a stated review and a guard summary that lists what remains on the server.
- No GIF is published without the owner's named go.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.
