# WP-112: Design a retry for skipped tool calls on the single-shot graph shape

- **State:** Not started (2026-09-02).
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

## Open design questions (this WP's actual deliverable before any code)

- **Detection**: how does `reason_node` (or a wrapping node) decide a
  tool-call was skipped when it should have happened? Regex/keyword
  matching on the reply text ("j'utilise generate_image") is the cheapest
  option live-observed today, but is it robust enough, or does it need a
  second, cheap classifier call - and is that proportionate?
- **Scope**: does the retry apply to every tool on the single-shot shape,
  or only `generate_image`/`generate_diagram` (the two cases with live
  evidence)? A narrow scope is safer but risks becoming another
  case-by-case patch instead of a real fix.
- **Retry shape**: a second full `reason_node` call with the narrated
  attempt fed back as context (mirroring `_resolve_diagram_generation_call`'s
  one-shot pattern), or something structurally different for a "no tool
  call" case vs. a "failed render" case?
- **Failure mode**: what happens if the retry *also* narrates instead of
  calling? One-shot only (matching the existing render-retry precedent), or
  does this case warrant a different fallback (e.g., an explicit
  system-level nudge, or surfacing a clarifying question to the user
  instead of silently failing)?
- **Cost/latency**: a second model call on every skipped-tool-call case adds
  real latency and token cost to Comage's already-loaded single-shot path -
  worth quantifying against ADR-0511's quota budgets before committing to a
  design.

## Acceptance checks (for this WP's own scope)

- A written, reviewed design (this WP's brief, updated in place, or a
  short design doc it links to) answering the open questions above, with a
  concrete `reason_node`/graph-shape diff proposed but not yet merged.
- `python3 platform/docs/check_docs.py` exits 0.
- No code changes to `agent-runtime` are required to close this WP if the
  design itself is the deliverable - a follow-up WP executes it. Judge at
  design time whether execution belongs in this same WP or a new one.

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
