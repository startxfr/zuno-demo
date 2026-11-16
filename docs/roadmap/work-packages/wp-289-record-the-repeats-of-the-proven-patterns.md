# WP-289: Record the repeats of the proven patterns

- **State:** Repo work merged (2026-11-16: 11 of 18 demos published; the other seven wait for the owner's decisions and go)
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
demos of this brief, **11**: `gitops-day0-3`, `image-signing-admission`, `external-models`, `ai-gateway-sovereignty`,
`okf-signed-agent-release`, `service-mesh-kiali`, `lightspeed`, `model-catalog-registry`, `mcp-tools-by-group`,
`ai-gateway-routing` and `evaluation-trustyai-evalhub`. With `open-webui`, `vault-pki` and the four of
[WP-288](wp-288-record-the-first-batch-of-browser-demos.md), the catalogue has **17 GIFs of 30 demos**.

**Seven demos of this brief are not published.**

- `dify`: row 0:45 shows real Confluence page titles on a frame, and the repository is public. The owner decided on 2026-11-16, 13:12 CET, that the take may show them (deferred entry d, order below). The run log it leaves cannot be deleted by the user.
- `guardrails`: rows 0:45 and 2:00 need Dify's own admin password, a second credential (deferred entry c; the owner allowed it on 2026-11-16, 13:12 CET, never in git). The Grafana half
  is no longer blocked: the Grafana sign-in now authorizes once and closes the announcement as declared changes.
- `unifai-agents`: two personas; not scouted.
- `observability-trace`: the Tempo half is wholly unscouted and the page says "not rehearsed"; the possible simplification is
  Grafana Explore on a Tempo data source (not checked).
- `aap-audited-operations`: no AAP helper in the recording chain, and the Keycloak sign-in to AAP was never proven on demo333.
  The row must show the job's Details tab, not its Output.
- `quotas`: one live screen only; a GIF of the script alone would be thin.
- `lora-pipeline-mlflow-kueue`: the pages name pipeline versions `v0-4-0-*` that the cluster does not list on 2026-11-16
  (deferred entry i); stills only, after the cause is known.

**Follow-ups outside this brief, all in the evidence file:** the deferred list (entries a to k: platform, agents or UnifAI
changes that the sprint rule forbade); the Grafana user-storage entry and the OAuth authorization of `ai-ops-01` that now stay
on the cluster; the stored effect of kagent's **Skip wizard**; the sprint's lesson that marker images are not enough for a chat
answer (scan the frames of each answer span).

Rows that carried "(untested command)" or "(untested prompt)" and were run by a published take have the mark lifted. The marks
that remain belong to rows no take has run.

## Owner's order of 2026-11-16, 13:12 CET

As given in `zuno-demo-reorg`'s session and relayed by it. The owner asked to continue, with the team of agents, on `dify`,
`guardrails`, `quotas`, `observability-trace`, `aap-audited-operations`, `lora-pipeline-mlflow-kueue` and the demos planned next, and
said they are OK with the information shown by `dify`, `guardrails` (as long as the password is not shown in git),
`mcp-tools-by-group` and `model-serving-llmd-mig`. So: `dify` may show real Confluence page titles; `guardrails` may use Dify's own
admin password as a second credential, never in git; `mcp-tools-by-group` row 1:30 may be shown in full and its re-take replaces the
published GIF; `model-serving-llmd-mig` may show the `NODE` column and its re-take replaces the published GIF. The decisions
that the hand-over above calls "the owner's" for `dify` and `guardrails` are therefore given. Each GIF still needs the owner's go
before it is published. Details and the split of the work: [the sprint evidence](../evidence/wp-289-gif-sprint-2026-11-16.md).
