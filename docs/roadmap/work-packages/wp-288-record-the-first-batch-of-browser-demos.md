# WP-288: Record the first batch of browser demos

- **State:** Done (2026-11-16)
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
3. **`identity-personas`** (two personas): several videos in one take, one persona after the other. Owner's decision of 2026-11-15: the contrast is shown by a question, not by the tools button (the Open WebUI screen shows one connection, **Zuno tools**, for every persona). Each persona starts a new chat and asks the same short question (candidate wording "Which tools can you use?", fixed after the scout), and the answer names three tools for sale-01 and six for consultant-02. So the take creates one chat per persona, deleted by its id, and the multi-video contract is no longer proven at no cost. The page rows are reworded to match; they are committed with the question marked untested, and the "You should see" cells say what is expected, not what was seen, until a take confirms it. If the answers do not name the tools, the fallback goes back to the owner: say that the tools are not shown, or show the tool-policy file as a still.
4. **`model-serving-llmd-mig`:** a terminal part and a Grafana panel, and the first OpenShift or Keycloak console sign-in. About a day.

Every sign-in flow other than the Keycloak form and every delete-by-id call outside Open WebUI is checked by a scout before the first take.

## Acceptance

- Each demo has a scout, a take that lists what it created and cleaned, a reviewed set of images and a stated number of sampled frames, and a GIF inside the limits.
- Each GIF is published only after the owner's named go; the page rows that could not appear on screen are settled.
- `python3 platform/demo/consistency.py` (0 problems) and `python3 platform/docs/check_docs.py` pass.

## Decision of 2026-11-16: the kagent first-run wizard

The first-run wizard of kagent stops the `kagent` scout. The owner allowed the **Skip wizard** click as a declared
change of the walkthrough. The click sends a `POST /` to kagent. What kagent stores because of it is not known. The
decision is stated in the guard summary of the take, and the stored effect stays an open point.

## Result (2026-11-16)

The four demos are recorded, reviewed and published on `devel`. Facts are in the
[sprint evidence](../evidence/wp-289-gif-sprint-2026-11-16.md).

| Demo | Take | Published in | Owner's go |
|---|---|---|---|
| `kagent` | `kagent-20261116-112558` | `6b130198` | the advance go "Go de publication pour kagent, unifai-live-rag et lightspeed" |
| `unifai-live-rag` | `unifai-live-rag-20261116-104643` | `2df2bf90` | "Les 12" at about 13:05 CET, with the earlier session titles visible (7.2 MB) |
| `identity-personas` | `identity-personas-20261116-101640` | `517a92ce` | "Les 12" |
| `model-serving-llmd-mig` | `model-serving-llmd-mig-20261116-095927` | `21bca7e2` | "Les 12" |

The `kagent` GIF also stands on a declared change: the **Skip wizard** click (decision above). The click sends one `POST` that a plain
reload also sends; the browser key is `kagent-onboarding` (as relayed from the scout). What kagent stores on the server is still
not known: an open point, not a blocker. `identity-personas` shows the contrast by a question, one chat per persona, deleted by
its id: `consultant-02` gets six tool names and `sale-01` three. `unifai-live-rag` is the pilot page
`docs/demo/unifai-live-rag.md`, not a page of the scenario catalogue. The first take of `model-serving-llmd-mig` was replaced by a
re-take whose commands print no node name.

The acceptance holds: each demo has a scout, a take that lists what it created and cleaned, a reviewed set of images with a stated
number of sampled frames, and a GIF under 8 MB. The owner's go is given in the owner's own words and relayed by `zuno-demo-reorg`.
