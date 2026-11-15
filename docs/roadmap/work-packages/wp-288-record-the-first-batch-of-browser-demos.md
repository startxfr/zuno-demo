# WP-288: Record the first batch of browser demos

- **State:** Not started
- **ADRs:** [ADR-0618](../../adr/0618-give-every-catalogue-scenario-a-gif-with-real-terminal-sessions-checked-as-text-first.md)
- **Depends on:** [WP-286](wp-286-improve-the-recording-chain-and-reprove-it-on-open-webui.md), [WP-287](wp-287-record-terminal-demos-as-real-sessions-checked-as-text.md)
- **Related:** [ADR-0617](../../adr/0617-record-the-demos-and-publish-them-as-gifs-with-the-owners-go.md), [WP-284](wp-284-record-the-open-webui-demo-and-publish-it-as-a-gif.md)
- **Target:** v0.16
- **Estimated files touched:** ~20: four walkthroughs, their cut lists, their evidence files and the page rows that need settling

> Why: ADR-0618 clause 14. Each of the four demos proves one new capability cheaply, so the repeats of WP-289 follow a proven pattern.

## Goal

`kagent`, `unifai-live-rag`, `identity-personas` and `model-serving-llmd-mig` are recorded, reviewed and published, each with the owner's named go.

## Steps

1. **`kagent`** (ai-ops-01): the second browser application with one persona and an existing browser check; one chat session to delete by its id (to verify by a scout). The row that reads a Secret and shows the refusal is checked on the images.
2. **`unifai-live-rag`** (consultant-01): the UnifAI sign-in and the deletion of a session, which `unifai-agents`, `observability-trace` and `a2a-delegation-approval` reuse.
3. **`identity-personas`** (two personas): several videos in one take, no prompt and nothing created, so the multi-video contract is proven at no cost. Its rows 2:30 and 3:30 name the tools button of Open WebUI: settle the page first, so that it claims only what the screen shows.
4. **`model-serving-llmd-mig`:** a terminal part and a Grafana panel, and the first OpenShift or Keycloak console sign-in. About a day.

Every sign-in flow other than the Keycloak form and every delete-by-id call outside Open WebUI is checked by a scout before the first take.

## Acceptance

- Each demo has a scout, a take that lists what it created and cleaned, a reviewed set of images and a stated number of sampled frames, and a GIF inside the limits.
- Each GIF is published only after the owner's named go; the page rows that could not appear on screen are settled.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.
