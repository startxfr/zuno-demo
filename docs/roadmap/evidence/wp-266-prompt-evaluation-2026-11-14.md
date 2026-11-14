# WP-266: evaluation of the six new prompts of the active agents (2026-11-14)

Session zuno-okf ran this test live on demo333 with the user's go. It compares the system messages served before
agents v1.0.0 with the prompts of v1.0.0, using the `prompt_examples` of each task.

## Scope

zuno-demo-agents v1.0.0 gives a prompt to six tasks of active agents that had none:
- tekos: `check-my-drive-docs`, `find-relevant-docs`, `write-code`;
- comage: `check-my-drive-and-mail`, `update-opportunity-status`;
- arkos: `write-code`.

Before v1.0.0, the operator built their system message from the agent description and the task body. Those task
bodies were design notes ("no distinct Agent Runtime route exists for it yet in v0", `GraphFactory`, the Codestral
credit policy), so the model received them as instructions.

## Method

A one-shot Job in `zuno-ai-run` sends each of the 15 `prompt_examples` to the task's workflow through UnifAI, the
same path as the UI. The primary task's workflow is named after the agent; any other task's workflow is
`<agent>-<task>`.
- Wiring: the acceptance gate's ServiceAccount, NetworkPolicy label and Secret, so the persona password never leaves
  the cluster.
- Personas: `consultant-01` for tekos and arkos, `sale-01` for comage.
- Recorded per example: the tool calls of the stream and the reply.
- Safety: the stream stops at the first `salesforce.opportunity.update` call, so the test never writes to Salesforce.
- Clean-up: the sessions are deleted at the end, then the Job and its ConfigMap.

The script and cases are in the session scratchpad of zuno-okf. This page records the results.

## Static review before the run

Comparing the two texts found one defect in the new prompts. Four of them named legacy tool-policy names
(`list_drive_files`, `search_confluence`, `read_gmail`). The mcp-gateway front door offers tools under their
capability (`drive.document.search`, `confluence.page.search`, `gmail.message.read`), so the model never sees those
names.

zuno-demo-agents PR #53 fixed the four prompts: tekos ×2, advantage and finage. `validate_okf_bundle.py` now refuses
a prompt or skill that names a legacy tool name.

## Baseline: old system messages (agents v0.14.4 bundles, operator 0.1.70), 06:57-07:06 UTC

| Task | Example | Tools called | Result |
|---|---|---|---|
| tekos check-my-drive-docs | satellite run architecture | `drive.document.search` | The delegated Google credential is absent for the persona; the agent says so and lists nothing |
| tekos check-my-drive-docs | Keycloak migration | `drive.document.search` | Same |
| tekos find-relevant-docs | satellite build architecture | none | Lists real Confluence pages with URLs from the pre-retrieved context (57 s) |
| tekos find-relevant-docs | OpenShift AI model serving | none | Lists docs.redhat.com guides with URLs (26 s) |
| tekos find-relevant-docs | Keycloak realm configuration | none | Lists internal procedures (34 s) |
| tekos find-relevant-docs | my Drive files on the upgrade | `drive.document.search` | No credential, then generic advice and RAG content |
| tekos write-code | Ansible wait for rollout | none | Correct task (2 s) |
| tekos write-code | NetworkPolicy from istio-system | none | Correct manifest (2 s) |
| tekos write-code | Go RS256 JWT against JWKS | none | A stub that calls an undefined function: weak |
| comage check-my-drive-and-mail | Drive and mail on the Startx account | `drive.document.search`, `gmail.message.read` | No credential; answers in slang, because comage routes to the `qwen3.5-9b-wesh` fine-tune by design |
| comage check-my-drive-and-mail | renewal negotiation emails | `gmail.message.read` | Same |
| comage update-opportunity-status | move Startx renewal to Negotiation | `salesforce.opportunity.update` | Stopped at the call (expected tool) |
| comage update-opportunity-status | "this opportunity", close date | `salesforce.opportunity.update` | **Calls the write tool without knowing which opportunity** |
| arkos write-code | Helm Route template | none | `Error code: 422`: no model is eligible at C3 (open, not caused by the prompt) |
| arkos write-code | Argo CD wait script | none | Same |

The arkos `write-code` 422 does not come from the prompt. The strict Codestral pin of ADR-0417 meets Arkos's C3, where
Codestral is not eligible. User decision of 2026-11-14: Arkos `write-code` moves to the local gpt-oss-20b, and Tekos
`write-code` stays the Codestral example. The change is committed for agents v1.0.1 and is not part of v1.0.0, so the
"after" run below still expects 422 for this task.

## After: prompts of agents v1.0.0 (operator 0.1.71), 10:23-10:25 UTC

Same Job, cases and personas. The agents ran the v1.0.0 bundles (tekos `f1ba6c45`, comage `36406124`, arkos `434cbd91`),
and the new prompts were the served `system_message` (checked on the `UnifaiAgent` objects).

| Task | Example | Tools called (before → after) | Result after |
|---|---|---|---|
| tekos check-my-drive-docs | ×2 | `drive.document.search` → same | Says plainly that the delegated credential is missing; shorter, no setup advice |
| tekos find-relevant-docs | 3 documentation/Confluence questions | none → none | A list of items, each with title, source, URL and one line of relevance, as the prompt asks (22-41 s, against 26-57 s) |
| tekos find-relevant-docs | my Drive files on the upgrade | `drive.document.search` → same | No credential, then related documentation from the context |
| tekos write-code | Ansible, NetworkPolicy | none → none | Correct code |
| tekos write-code | Go RS256 JWT | none → `time.get_current_time` | **No code, a one-line answer in slang.** Not caused by the prompt: Mistral Codestral answered 429 "Rate limit exceeded" (ai-gateway log, 10:24:12 and 10:24:14), and the chain fell back to its second model `local-wesh-maas` (qwen3.5-9b-wesh), whose reasoning block was served as content |
| comage check-my-drive-and-mail | ×2 | same tools → same | No credential, said plainly (slang, by design of the wesh model) |
| comage update-opportunity-status | move Startx renewal to Negotiation | `salesforce.opportunity.update` → same | Calls the write tool (stopped by the harness) |
| comage update-opportunity-status | "this opportunity", close date | `salesforce.opportunity.update` → **none** | **Asks which opportunity before writing anything**: the defect of the old system message is fixed |
| arkos write-code | ×2 | none → none | `Error code: 422`, unchanged: fixed by the routing change for agents v1.0.1 |

## Verdict

- The new prompts give no regression on the tools called.
- Two answers improve:
  - comage stops guessing the opportunity of a write;
  - tekos find-relevant-docs returns the structured list the task describes.
- WP-266's prompt evaluation passes.

Open points:
- **The Codestral rate limit.** Three quick requests at 10:24 UTC got 429. The golden path's `zuno-code` moment was served
  by Codestral at 10:21, so the limit is intermittent. It is a risk for the coding demo (Tekos `write-code`, "Zuno Code").
- **The fallback of Tekos `write-code`.** After Codestral comes `local-wesh-maas`, the slang fine-tune, and it produced no
  code. A follow-up for the agents policy: put `local-gpt-oss-maas`/`local-gpt-oss` (or the quality model) before the
  wesh pair for code. This needs the owner's decision, since ADR-0526 placed wesh second.
- **Delegation messages.** In the golden path's delegation-approval moment (Arkos to Tekos, approval rejected), the trace
  holds 4 A2A `send_message` spans after the promotion, against 2 before. The a2a-gateway logged 38 POSTs to Tekos
  (most are task polling). One sample each; to watch with Arkos scenario 21 (at most 3 messages).

## Agents v1.0.1: the coding pair and the delegation count (12:35-13:15 UTC)

v1.0.1 (corp `e205c34b`) was promoted with the owner's go at f33a332d:
- arkos `write-code` runs on the local gpt-oss-20b (#58);
- tekos `write-code` falls back to gpt-oss-20b instead of the wesh fine-tune (#57).

The golden path passed 13/13 before and after. The same one-shot Job ran each turn, and Tempo gave the
ai-gateway's `model_call` spans of each run:

| Run | Model calls (provider@level) | Result |
|---|---|---|
| tekos `write-code`, NetworkPolicy request | 1 × `mistral-codestral@C1` | The manifest, in 1.8 s |
| arkos `write-code`, the same request | 11 × `local-gpt-oss-maas@C3` | The manifest with a namespace placeholder, in 23 s. The 422 is gone |
| arkos delegation to tekos (scenario 21 prompt), run 1 | 38 × `local-gpt-oss-maas@C3` | 5 A2A `send_message`: **above the bound of 3** |
| same, run 2 | 26 × `local-gpt-oss-maas@C3` | 3 A2A messages |
| same, run 3 | 24 × `local-gpt-oss-maas@C3` | 3 A2A messages |

Both halves of the coding pair are proven. The repeated delegation shows in about one run out of three:
- The golden path's delegation-approval moment served 6 calls before and 6 after v1.0.1. The 38 calls seen once after
  v1.0.0 were a one-off.
- The repetition belongs to the operator's delegation loop, and it was reported to the fork maintainers. It is not
  caused by the prompts.
