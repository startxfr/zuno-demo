# WP-112: Design a retry for skipped tool calls on the single-shot graph shape

- **State:** Repo work merged (2026-09-02) - design answered below,
  implemented in the same pass (judged in-scope, see "Design vs.
  execution" below), unit-tested
  (`components/agent-runtime/tests/test_reason_node_narration_retry.py`, 5/5
  PASS, full existing suite green). Live-verified against a real
  `qwen3.5-9b-wesh` deployment: the retry mechanism itself is confirmed
  working (server-side logs show Comage genuinely invoking
  `generate_image` for the first time, where it previously only
  narrated) - a clean `images=1` PASS on the two named regression checks
  is currently blocked by two separate, live, unrelated infra conditions
  (an external SDXL-provider outage and a concurrent MaaS auth 401
  burst), not by anything in this WP's own code. See "Live verification"
  below for the full evidence and what's needed to re-confirm once those
  clear.
- **ADRs:** ADR-0516 (Decision - the tool-schema/prompt contradiction ADR-0516
  accepted as an unmitigated risk; that risk has now manifested with live
  evidence). ADR-0516 itself stays `Implemented`/v0.4 - this WP does not
  reopen it, it schedules the follow-up work its own "Accepted risks"
  section already anticipated.
- **Depends on:** none (the schema/prompt contradiction this builds on top
  of is already fixed, commit `ef7b5c43`, 2026-09-02).
- **Unblocks:** none known yet.
- **Related:** ADR-0526 (`qwen3.5-9b-wesh`'s already-documented
  narrate-instead-of-call behavior, 2026-08-29 Amendment) - this WP is
  where that behavior's consequence for tool-calling reliability gets a
  real fix, rather than being re-discovered per agent/task.
- **Target:** v0.9.

## Goal

Comage's `check-deal-status` task narrates using `generate_image` instead of
actually invoking it, for prompts using the word "mockup" - live-confirmed
2026-09-02 even after fixing the tool-schema/system-prompt contradiction
that originally looked like the whole problem (see "Out of scope /
deferred" below). This WP is scoped to *designing* a fix - a
disambiguation/retry turn for `agent-runtime`'s single-shot
`retrieve_reason_respond` graph shape when a tool was offered in a turn but
never called - not to implementing one yet. `reason_node`
(`components/agent-runtime/app/graph/nodes.py:791-938`) is shared by every
agent on that graph shape, not just Comage, so this changes shared runtime
behavior and needs its own scoped design pass before any code changes.

## ADR references

ADR-0516's "Accepted risks" section (`docs/adr/
0516-generate-diagrams-with-self-hosted-mermaid-rendering.md:167-174`)
already named the tool-schema wording ambiguity as an accepted risk with
"remediation: none beyond the description wording" - explicitly
"speculative ahead of real usage data." That data now exists (see
Preconditions below); this WP is the design pass the ADR deferred, not a
new decision reopening it.

## Preconditions (verify before starting)

- Read the live evidence first: `docs/roadmap/evidence/
  adr-0516-diagram-render.md`'s "Follow-up (2026-09-02)" section, and this
  WP's own referenced stresstest artifacts:
  `evaluations/comage/stress_test.py::img-mockup_request` and
  `evaluations/comage/security_checks.py::
  comage_chat_uses_photorealistic_images_only_for_marketing_visual_requests`
  - both fail today with `images=0`/`images=[]` and a reply narrating tool
  use instead of invoking it.
- Read `components/agent-runtime/app/graph/shapes/
  retrieve_reason_respond.py` and `nodes.py`'s `_make_reason_node`/
  `reason_node` (`nodes.py:791-938`) in full - confirm which other agents
  actually run this shape today (Comage confirmed; check Advantage/Finage/
  Naveo) before assuming the blast radius.
- Read `_resolve_diagram_generation_call`
  (`nodes.py:1130-1238`) as the existing precedent for a retry - it only
  retries a *failed render after a tool call happened*, which is a
  narrower and safer case than "no tool call happened at all." Understand
  exactly why that's narrower before designing this WP's retry (a
  render-failure retry has an unambiguous trigger - an error string from
  the render service; a skipped-tool-call retry has to *infer* that a
  tool should have been called from prose alone, which is a much fuzzier
  signal and the real design risk here).
- Confirm current `qwen3.5-9b-wesh` narration-rate data
  (`docs/adr/0526-...md`'s 27-probe eval set) doesn't already cover this
  exact "mockup" scenario - if it doesn't, decide whether extending that
  eval set is part of this WP's own acceptance evidence or a separate
  follow-up.

## Design (2026-09-02)

Preconditions verified: `retrieve_reason_respond` is used by five agents
(`components/agent-runtime/app/graph/shapes/retrieve_reason_respond.py`) -
Tekos, Comage, Advantage, Finage, Naveo (Arkos uses `plan_draft_write`, a
different shape, even though it shares the `reason_node`/`_make_reason_node`
factory - out of this WP's scope, which only names `retrieve_reason_respond`
users). Of those five, only Comage and Tekos declare `diagram.generation.create`
and only Comage declares `image.generation.create` (Tekos's own task file
explicitly documents never declaring it -
`agents/tekos/tasks/answer-technical-question.md:14`).

The eval-set precondition (does the current narration-rate data already
cover this) came back **no**: ADR-0526's 27-probe
`tool_calling_conformance.py` corpus measures 0% narration on the revised,
currently-deployed corpus, but has zero probes using "mockup" wording - the
exact live-failing phrasing (`evaluations/comage/stress_test.py:115`). This
is the same wording-sensitivity pattern already found for Arkos's
`generate_diagram` gap (imperative "draw" passes, "schema"/buried-request
phrasing fails) - narration is not the systemic 46.7%-rate defect the
Amendment fixed, it is a rarer, phrasing-specific residual on top of an
otherwise-working fix.

## Open design questions - answered

- **Detection**: regex/keyword matching, not a second classifier call - and
  narrower than "any keyword": the literal offered tool name
  (`generate_image`/`generate_diagram`) appearing verbatim in the reply
  text with zero `tool_calls`. Organic prose is very unlikely to contain
  either literal string, so this stays a low-false-positive signal without
  the cost of a second model call on every turn. A second classifier call
  was rejected as disproportionate precisely because the eval-set finding
  above shows this is a rare, phrasing-specific residual, not a systemic
  rate that would justify always paying for a classifier.
- **Scope**: `generate_image`/`generate_diagram` only - the two cases with
  live evidence - but implemented as a generic check over whatever visual
  tool schemas `reason_node` actually offered that turn
  (`_VISUAL_TOOL_NAMES`), not two hardcoded string checks. Git-forge tools
  are excluded: `_resolve_git_forge_calls` already has its own multi-round
  resolution shape, and extending detection there without live evidence of
  the same defect would be exactly the "case-by-case patch" risk this
  question warns about. The mechanism generalizes cleanly if that evidence
  ever appears.
- **Retry shape**: structurally different from
  `_resolve_diagram_generation_call`'s render-failure retry, not a copy of
  it - that precedent has a real `ToolMessage` to feed back (a call *did*
  happen, it just errored). Here no call happened at all, so there is
  nothing truthful to put in a `ToolMessage`. The new helper
  (`_retry_narrated_visual_tool_call`, `components/agent-runtime/app/
  graph/nodes.py`) feeds the assistant's own narration back as a plain
  `AIMessage` plus an explicit `HumanMessage` nudge ("you said you would
  use a tool but did not call it"), then re-offers the same visual tool
  schemas for one bounded retry round.
- **Failure mode**: one-shot only, matching the render-retry precedent's
  hard cap. If the retry also narrates (or answers differently in prose),
  its own words become the final reply - not the original narration, and
  not a surfaced error, mirroring `_resolve_diagram_generation_call`'s own
  "retry produced no call -> use its words" branch. A provider failure on
  the retry round falls back to the *original* narrated reply instead
  (already a valid answer) rather than surfacing a system error the user
  did not cause.
- **Cost/latency**: bounded by the detection being narrow rather than by
  rate-limiting the retry itself - it only fires on the rare, now-measured
  residual (not the old 46.7% baseline), so the ADR-0511 quota class draws
  down by one extra call only on that already-rare path. Quantifying the
  real-world firing rate needs the eval-set gap above closed first (a
  "mockup"-worded probe added to the 27-probe corpus); tracked as a
  follow-up rather than blocking this WP, since it is ADR-0526/WP-087
  territory (a different corpus owner) and the fix itself does not depend
  on that number.

## Design vs. execution

Judged in-scope for this same WP rather than deferred to a follow-up: the
design above is fully bounded (one new helper, one call site, no new state
fields, no cross-agent config), mirrors an existing merged precedent
almost exactly, and the whole point was to unresolve a currently-failing
regression check
(`evaluations/comage/stress_test.py::img-mockup_request`,
`evaluations/comage/security_checks.py::
comage_chat_uses_photorealistic_images_only_for_marketing_visual_requests`).
Implemented in `components/agent-runtime/app/graph/nodes.py`
(`_VISUAL_TOOL_NAMES`, `_NARRATED_TOOL_NAME_PATTERN`,
`_retry_narrated_visual_tool_call`, wired into `_make_reason_node`'s
`reason_node` closure right before its final tool-less-reply fallback).
Covered by 5 new unit tests
(`components/agent-runtime/tests/test_reason_node_narration_retry.py`,
built against Comage's own `check-deal-status` task via `_make_reason_node`
directly - the exact (agent, task) pair the live defect was found on):
retry succeeds after a narrated `generate_image`; retry also narrates and
its own words become the final reply; a `ModelRouterError` on the retry
falls back to the original reply; a plain answer that never names a
visual tool is not retried; a genuine first-attempt tool call bypasses the
retry path entirely. Full existing `components/agent-runtime` suite
re-run clean alongside it (no regression).

## Live verification (2026-09-02) - mechanism confirmed, end-to-end PASS blocked by unrelated infra

Pushed (`5e7ee40b`), `agent-runtime`/`agent-frontend` rebuilt and re-signed
(RHTAS), then re-ran `make d3 stresstest agents` (BULK=0) live against
`qwen3.5-9b-wesh`/Comage's real `check-deal-status` route with the
`sale-01` persona (this stress test's own persona, not `consultant-01` -
that was this brief's own earlier inaccuracy, corrected here).

**The retry itself works, confirmed from server-side logs, not just the
HTTP response body:**

```
mcp-gateway:  tool=generate_image capability=image.generation.create
              agent=comage task=check-deal-status allowed=True
              reason=allowed request_id=a05d7dfb...
ai-gateway:   image_call: provider=ovhcloud-sdxl model=stable-diffusion-xl-base-v10
              classification=C2 request_id=224457d7...
```

Before this fix, Comage's "mockup" prompt never reached MCP Gateway or
ai-gateway at all - the model narrated in prose and no tool call was ever
made (that is the whole defect this WP exists to fix). This log evidence
is the real proof: the retry detected the narration, re-offered the tool,
and the model actually called it this time - two independent live
occurrences (the stress test's own `img-mockup_request` and the security
check's marketing-visual probe both triggered a real `generate_image`
invocation for the first time).

**Both checks still report FAIL** (`images=0`), but for two reasons
downstream of the retry succeeding, neither in this WP's scope:

1. `ai-gateway` logs: `image provider 'ovhcloud-sdxl' failed: Connection
   error` -> `502 Bad Gateway` on `/v1/images/generations` - OVHcloud's
   external SDXL endpoint was unreachable from the cluster at test time.
   An external-service outage, not a code defect.
2. On that tool error, `_resolve_image_generation_call`'s existing
   follow-up (tool-less) call is supposed to compose an apologetic reply
   - this time it came back with empty content instead, the same known
   "model had nothing more to say" degenerate case already documented and
   handled (without crashing) for Arkos
   (`test_draft_node_then_reflect_node_survives_an_empty_image_caption`).
   Concurrent with the test window, `ai-gateway` logs show a live,
   unrelated MaaS auth problem - `local-wesh-maas`/`local-gpt-oss-maas`
   both returning `Error code: 401` in a sustained burst (61 occurrences
   in the prior 2h, still ongoing, affecting callers other than Comage
   too) - plausibly what pushed that particular follow-up call into the
   degenerate empty-content path. Neither the SDXL outage nor the MaaS
   401 burst is caused by, or fixable within, this WP.

**Re-run once both external conditions clear** to get a clean `images=1`
PASS on both checks - the retry mechanism itself needs no further code
change; this is now an infrastructure-availability gate, not a design or
implementation gap.

## Acceptance checks (for this WP's own scope)

- A written, reviewed design (this WP's brief, updated in place, or a
  short design doc it links to) answering the open questions above, with a
  concrete `reason_node`/graph-shape diff proposed but not yet merged. -
  **done**, see "Design (2026-09-02)"/"Open design questions - answered"
  above; judged in-scope for execution too, see "Design vs. execution".
- `python3 platform/docs/check_docs.py` exits 0. - **done**.
- No code changes to `agent-runtime` are required to close this WP if the
  design itself is the deliverable - a follow-up WP executes it. Judge at
  design time whether execution belongs in this same WP or a new one. -
  judged in-scope, see "Design vs. execution"; live-verified against a
  real deployment - retry mechanism confirmed working, full PASS blocked
  by unrelated infra, see "Live verification" above.

## Out of scope / deferred

- The tool-schema/system-prompt contradiction itself - already fixed,
  commit `ef7b5c43`, 2026-09-02, live-verified (the model now correctly
  reasons `generate_image` is the right tool for a marketing mockup
  request; it just doesn't call it).
- Arkos's `generate_diagram` non-call gap - unrelated root cause (a missing
  system-prompt instruction, not narration), already fixed separately,
  commit `b0cb07f4`, 2026-09-02, live-verified 3/3 PASS.
- Any change to `qwen3.5-9b-wesh`'s fine-tune/training data (ADR-0526's own
  scope) - this WP treats the model's narration behavior as a given
  runtime constraint to design around, not something to retrain away.

## Status updates

- On design completion (open questions above answered, diff proposed):
  State -> "Repo work in review" if a companion PR exists, otherwise stays
  "Not started" with the design recorded in this file until a follow-up WP
  picks up execution.
- 2026-09-02: design answered and implemented in the same pass (see
  "Design vs. execution") - State -> "Repo work merged". Live-verified the
  same day: retry mechanism confirmed working from server-side logs (see
  "Live verification"), but a clean `images=1` PASS on both named
  regression checks is blocked by two unrelated, live infra conditions
  (SDXL provider outage, MaaS 401 auth burst), not by this WP's code.
  Moves to "Done" once those clear and a re-run confirms both checks
  green - re-running `make d3 stresstest agents` (or targeting Comage
  specifically once that's supported) is then the only remaining step,
  no further code change expected.
