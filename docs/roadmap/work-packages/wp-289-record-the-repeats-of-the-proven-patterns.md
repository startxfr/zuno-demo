# WP-289: Record the repeats of the proven patterns

- **State:** Done (2026-11-17: 18 of 18 demos published; the limits are written below)
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

## Progress and hand-over (2026-11-16)

The night sprint of 2026-11-16 and the morning that followed are in the
[sprint evidence](../evidence/wp-289-gif-sprint-2026-11-16.md). Published on `devel`, each with a stated review: of the 18
demos of this brief, **18**: `gitops-day0-3`, `image-signing-admission`, `external-models`, `ai-gateway-sovereignty`,
`okf-signed-agent-release`, `service-mesh-kiali`, `lightspeed`, `model-catalog-registry`, `mcp-tools-by-group`,
`ai-gateway-routing`, `evaluation-trustyai-evalhub`, `aap-audited-operations`, `quotas` (the two on the owner's go of 18:36 CET), `unifai-agents` and `lora-pipeline-mlflow-kueue` (the two on the owner's go of 21:30 CET) and `dify` (the owner's go of 23:18 CET), `guardrails` (the owner's go of 05:18:40 CET on 2026-11-17) and `observability-trace` (the owner's go of 11:37:38 CET on 2026-11-17; the coordinator's log, as relayed). With `open-webui`, `vault-pki` and the four of
[WP-288](wp-288-record-the-first-batch-of-browser-demos.md), the catalogue has **27 GIFs of 30 demos** (from WP-290: `genai-playground`, `maas-portal-api-keys` and `openclaw`).

**All 18 demos of this brief are published.** Their notes:

- `dify` is published (take `dify-20261116-215039`, commit `00a57123`). Every `dify` take moved the Zuno Agent's edited date at its Agent turn in Debug & Preview (three times on 2026-11-16); the take under the default-deny guard sent no configuration write for the Agent. The owner declared the effect ("Yes, declared effect", as relayed). The workflow run stays in Dify's run log. The Agent's content was never compared with a reference.
- `guardrails` is published (take `guardrails-20261116-233501`, commit `e75b0ce8`, on the owner's go of 05:18:40 CET on 2026-11-17, as relayed). The panel's count includes the probes of the demo's own check, and the page says so. The take's agent turn moved the Zuno Agent's edited date again (declared). It used Dify's administrator account as a second credential, never written in git.
- `observability-trace` is published (take `observability-trace-20261117-071006`, commit `6b57720c`, on the owner's go of 11:37:38 CET on 2026-11-17, as relayed). The two earlier trace takes had failed (a selector bug, then tags scrolled out of the window); the passing take followed the coder's framing fixes and a clean rescout. The page's row 5:00, the Grafana step, stays "not rehearsed": the take did not run it.

**Follow-ups outside this brief, all in the evidence file:** the deferred list (entries a to r: platform, agents or UnifAI
changes that the sprint rule forbade); the Grafana user-storage entry and the OAuth authorization of `ai-ops-01` that now stay
on the cluster; the stored effect of kagent's **Skip wizard**; the sprint's lesson that marker images are not enough for a chat
answer (scan the frames of each answer span).

Rows that carried "(untested command)" or "(untested prompt)" and were run by a published take have the mark lifted. The marks
that remain belong to rows no take has run.

## Closed on 2026-11-17: the limits, written

The owner chose **"Clore, limites écrites"** (close, limits written) in `zuno-demo-reorg`'s session, answered at 12:03:21 CET on 2026-11-17 (read there in its log, as relayed), after being told: 18 GIFs published, each on a named go; the guard table rests on the takes' files at `0350cd2f`; the takes before the write guard have no measured absence of writes; `ai-gateway-sovereignty` makes two real model calls. Not chosen: close after converting the published walkthroughs to the guard; leave the brief open. The table is in [the afternoon evidence](../evidence/wp-289-gif-afternoon-2026-11-16.md), section "Guard summaries of the 18 demos of WP-289".

**The limits of what this brief records:**

- **No measured absence of writes for the takes before the write guard.** `model-catalog-registry`, `ai-gateway-routing`, `evaluation-trustyai-evalhub`, `quotas`, `unifai-agents`, `lora-pipeline-mlflow-kueue`, `lightspeed` and `mcp-tools-by-group` have no `writes` key in their `markers.json`; `aap-audited-operations` has none either. They are read-only or declared by their walkthrough and by the counts of created and owned objects, not by a measured guard. The published walkthroughs were not converted to the shared guard.
- **`ai-gateway-sovereignty` is not read-only.** Its golden-path probe makes two real model calls from inside the gateway pod; they stay in the platform's records.
- **Records.** The record log is absent from the cache for the six terminal takes (`gitops-day0-3`, `image-signing-admission`, `external-models`, `ai-gateway-sovereignty`, `okf-signed-agent-release`, `service-mesh-kiali`). `markers.json` has no `writes` key for `dify`, `guardrails` and `lora-pipeline-mlflow-kueue`; the writes of the first two are in their record logs.
- **The guard sees HTTP only.** A WebSocket is not seen (the `openclaw` Control UI, of WP-290).
- **Declared effects:** the Zuno Agent's edited date in Dify (`dify`, `guardrails`) and the run log that `dify` leaves.

**Left open, each where it is recorded** (nothing is closed by this state): the deferred entries a to r (the sprint evidence); the Playwright pin on `main`; the AAP user `consultant-03`; the Grafana step of `observability-trace` row 5:00, not rehearsed; the Tempo and Grafana authorizations that stay on the cluster; the declared effects.

## Owner's order of 2026-11-16, 13:12 CET

As given in `zuno-demo-reorg`'s session and relayed by it. The owner asked to continue, with the team of agents, on `dify`,
`guardrails`, `quotas`, `observability-trace`, `aap-audited-operations`, `lora-pipeline-mlflow-kueue` and the demos planned next, and
said they are OK with the information shown by `dify`, `guardrails` (as long as the password is not shown in git),
`mcp-tools-by-group` and `model-serving-llmd-mig`. So: `dify` may show real Confluence page titles; `guardrails` may use Dify's own
admin password as a second credential, never in git; `mcp-tools-by-group` row 1:30 may be shown in full and its re-take replaces the
published GIF; `model-serving-llmd-mig` may show the `NODE` column and its re-take replaces the published GIF. The decisions
that the hand-over above calls "the owner's" for `dify` and `guardrails` are therefore given. Each GIF still needs the owner's go
before it is published. Details and the split of the work: [the sprint evidence](../evidence/wp-289-gif-sprint-2026-11-16.md).
