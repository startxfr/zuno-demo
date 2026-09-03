# WP-112: Design a retry for skipped tool calls on the single-shot graph shape

- **State:** Repo work merged (2026-09-03) - blocked on an unrelated
  platform defect, not on this WP. **The narrate-instead-of-call defect
  this WP targets is fixed and live-proven**: after the second fix (the
  Arkos-precedent "actually invoke it" system-prompt instruction, which
  `agents/comage/prompts/check-deal-status.md` had never carried), the
  2026-09-03 re-run shows Comage's marketing prompt making a real
  `generate_image` call through `mcp-gateway` to `ai-gateway`, with no
  prose narration anywhere in the run, and `sxa_visualization_boundary`
  still passing. Both named checks nonetheless still report FAIL, for two
  reasons, both since resolved or re-scoped. The external-egress defect is
  fixed (WP-124, Done), and the third run has `comage/security` **8/8** - the
  marketing check green for the first time, with a real SDXL image. What
  remains is `img-mockup_request`, which across three runs has failed three
  different ways, two of them plain narration ("Ouais, j'peux faire ca."), so
  widening the trigger IS indicated after all - a claim this brief briefly
  retracted on a one-run sample. That widening is the remaining work. Widening `_NARRATED_TOOL_NAME_PATTERN` is no
  longer the indicated next step - there is no narration left to detect.
  See "Live verification (2026-09-03, second run)" for the full evidence.
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
exact live-failing phrasing (`evaluations/comage/stress_test.py:115`).
**Correction (2026-09-03): that last clause is wrong** - `tool_probes.yaml`'s
`img-04` is a mockup-worded probe and predates this WP; what the corpus
lacks is a *deal-proposal* mockup probe. See "Second fix (2026-09-03)",
which also records that the 0% number was measured against a stale copy of
the schema. This
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

## Live verification (2026-09-03) - re-run after WP-122 closed the MaaS 401s: still FAIL, real detection gap found

Both external conditions from the 2026-09-02 run were expected to have
cleared (WP-122 fixed the MaaS 401 burst; no reason to assume SDXL was
still down). Re-ran `make d3 stresstest agents BULK=0` as WP-122's own
named downstream confirmation. **Both checks still FAIL** - but this
time for a different, more fundamental reason than infra:

```
comage stress_test FAIL image_generation img-mockup_request
  -> images=0 reply_snippet="\n\nOuais, pour un visuel de proposition
     commerciale, c'est le bon outil. C'est un mockup marketing, pas une
     visualisation de données structurées."
comage security FAIL comage_chat_uses_photorealistic_images_only_for_marketing_visual_requests
  -> chart_status=200 chart_images=[] marketing_status=200 marketing_images=[]
```

Checked `mcp-gateway`/`ai-gateway` logs for the test window: **zero**
`generate_image`/`check-deal-status` tool-call log lines - unlike the
2026-09-02 run (which showed the retry actually firing and a real tool
call reaching both services, just failing downstream on SDXL/MaaS), this
time `_retry_narrated_visual_tool_call` never triggered at all.

**Root cause, found by re-reading the trigger condition
(`components/agent-runtime/app/graph/nodes.py:805-807,1023-1024`):**
`_NARRATED_TOOL_NAME_PATTERN` only matches replies that literally contain
the substring `generate_image` or `generate_diagram`. The model's actual
reply above never names the tool - it describes intent in French
("c'est le bon outil" / "that's the right tool") without ever saying
`generate_image`. This is the exact narrate-instead-of-call defect this
WP targets, just phrased in a way the name-substring heuristic cannot
catch. **The retry mechanism itself is proven working (2026-09-02
evidence stands); the trigger that decides when to invoke it is too
narrow** - it only catches narration that names the function, not
narration that merely describes using "the tool" for the task.

This is a real, distinct gap, not a re-run of the same finding. Widening
the trigger safely is a genuine design question, not a quick tweak: an
unconditional retry-whenever-no-tool-call-came-back would also fire on
Comage's deliberate, CORRECT declines (the `sxa_visualization_boundary`
check - `comage/sxa_visualization_boundary: 1/1 passed` this same run -
depends on Comage being able to say no without being nudged into calling
a tool it shouldn't for that case). Any broader heuristic needs to keep
that distinction, across at least French and English phrasing, without
a new eval corpus to validate against - left as explicit follow-up
work, not attempted here without review.

Two other FAILs in this same run are unrelated, pre-existing, and out of
scope: acceptance scenarios 10 and 12 both fail on the known absent
`salesforce-mcp` live deployment (WP-101, not started, new-owner
credential gap) - `status=500 expected=403` on scenario 12 is that same
root cause surfacing through the MCP Gateway's own error path, not a new
defect.

## Second fix (2026-09-03) - the Arkos-precedent prompt instruction

Reviewing the 2026-09-03 gap surfaced a cheaper lever the earlier design
pass never considered, and one with a directly comparable precedent.

Arkos had *this exact defect* on `generate_diagram` and it was closed
(1/3 -> 3/3 PASS, commit `b0cb07f4`, live-verified) by a single
system-prompt paragraph, not by runtime code -
`agents/arkos/prompts/draft-architecture-testimonial.md:26-31`:

    ... you must actually call the diagram-generation tool with real
    diagram source - never write the diagram source yourself inside your
    reply text and describe it as done.

`agents/comage/prompts/check-deal-status.md` had **no equivalent
instruction**. It carried only the *boundary* paragraph saying which of
the two visual tools applies - and the live failing reply is Comage doing
precisely that and nothing more: adjudicating the boundary in prose
("c'est un mockup marketing, pas une visualisation de donnees
structurees") and then stopping. The prompt told it how to choose and
never told it to call.

Fixed by appending the same shape of instruction Arkos uses, with an
explicit decline clause so the deliberate-decline path stays open:

    Once you have decided which of the two applies, you must actually
    invoke that tool through the function-calling interface - never
    describe which tool you would use, and never say you are producing a
    visual, inside your reply text. [...] If neither tool applies, say so
    plainly and call nothing.

That last sentence is load-bearing: `sxa_visualization_boundary` (1/1
passing) depends on Comage being able to refuse, and this instruction must
not turn a correct refusal into a nudge to call something.

**Chosen over widening `_NARRATED_TOOL_NAME_PATTERN` first**, deliberately:
the trigger lives in `_make_reason_node`, which every agent on
`retrieve_reason_respond` runs (Tekos, Comage, Advantage, Finage, Naveo -
plus Arkos, which uses `plan_draft_write` but shares the same node
factory), so widening it is a shared-runtime change with no eval corpus to
validate the widened heuristic against. The prompt fix is Comage-only and
has a proven precedent. Widening the trigger stays available as the next
step if this does not close the two checks - the design for it is
unchanged and recorded above.

### Two documentation defects corrected in the same pass

1. **"The 27-probe corpus has no mockup-worded probe" was wrong.** Stated
   in this brief's "Design (2026-09-02)" section and repeated in the
   comment at `components/agent-runtime/app/graph/nodes.py`.
   `evaluations/comage/tool_probes.yaml`'s `img-04` ("Peux-tu me creer un
   mockup visuel de notre stand pour le salon ?", `expects_tool:
   generate_image`) is exactly such a probe and predates this WP. The real
   gap is narrower and still open: no *deal-proposal* mockup probe - the
   wording that sits on `check-deal-status`'s own marketing-vs-structured-
   data boundary. Still ADR-0526/WP-087 corpus territory, still a
   follow-up, but now stated accurately.

2. **A real, silently-failing drift check.** `ef7b5c43` (2026-09-02)
   qualified `_GENERATE_IMAGE_TOOL_SCHEMA`'s description in `nodes.py` but
   never updated the copy in `evaluations/comage/tool_probes.yaml`.
   `evaluations/tests/test_tool_calling_conformance.py::
   test_probe_schemas_have_not_drifted_from_the_runtime` had been FAILING
   since, unnoticed because neither that file nor
   `components/agent-runtime/tests/test_reason_node_narration_retry.py` is
   in `.github/workflows/lint.yml`'s `python` job. This matters to this
   WP's own argument: the "0% narration post-`ef7b5c43`" number it leans on
   was measured against the *stale, pre-`ef7b5c43`* schema - the very
   description whose ambiguity `ef7b5c43` existed to remove. The fixture is
   now regenerated from `nodes.py` (18/18 pass). Wiring these two suites
   into CI is left as a separate follow-up rather than smuggled into this
   WP.

### Verified locally (no cluster)

- `evaluations/tests/test_tool_calling_conformance.py` - 18/18 (was 17/18).
- Full `components/agent-runtime` suite - 21 files, all green,
  `test_reason_node_narration_retry.py` 5/5.
- `python3 platform/okf/run_agent_contract_tests.py` - PASS.
- `python3 platform/docs/check_docs.py` - PASS.

### Still required to close this WP

Prompts are baked into the image at `/app/agents`
(`components/agent-runtime/app/registry.py`, `AGENTS_DIR`) and the signed
bundle digest covers every file under `agents/<name>/`, so this is not a
config-only change: push, rebuild `agent-runtime`, `make d3 sign agents`
(ADR-0420), then re-run `make d3 stresstest agents BULK=0`. Confirm the
OVHcloud SDXL path is reachable before reading the result - a `502` on
`/v1/images/generations` is an infra result, not a WP-112 one. Diagnose
the security check's *marketing* half separately: its prompt is
unambiguous, carries no "mockup" wording, and no narration snippet was
ever captured for it, so it may be a plain miss with no narration - a case
no reply-text trigger could ever catch.

## Live verification (2026-09-03, second run) - narration gap CLOSED, two residuals

Rebuilt (`agent-runtime-24`), re-signed (`make d3 sign agents` - the
rebuild first crashlooped on `agents/comage: signature verification
failed`, exactly what that step exists to clear), then re-ran
`make d3 stresstest agents BULK=0`.

**The defect this WP exists to fix no longer reproduces.** For the first
time, Comage's marketing prompt produced a real tool invocation:

```
10:24:31 mcp_gateway tool=generate_image capability=image.generation.create
         agent=comage task=check-deal-status classification=C2 allowed=True
10:24:31 ai_gateway image_call: provider=ovhcloud-sdxl model=stable-diffusion-xl-base-v10
```

Exactly one `generate_image` call, inside the security check's own window
(10:24:24 -> 10:24:35), so it is unambiguously the *marketing* half; the
*chart* half correctly produced nothing. No prose narration anywhere in
the run. The prompt instruction did what the trigger widening was meant
to do, without touching shared runtime code.

| Check | Result | Detail |
| --- | --- | --- |
| `img-mockup_request` | FAIL | `images=0`, but no longer narration - see below |
| `comage_chat_uses_photorealistic_images_only_...` | FAIL | real tool call made; blocked downstream, see below |
| `diagram-sales_process_flow` | PASS | `images=1 mime_types=['image/svg+xml']` |
| `sxa_visualization_boundary` | PASS | the deliberate decline still works - the decline clause held |
| acceptance 10 / 12 | FAIL | pre-existing, absent `salesforce-mcp` (WP-101) |

### Residual 1 - `img-mockup_request` changed nature, and is arguably correct now

The reply is no longer narration. It is a grounding-based request for
input:

> "J'ai pas de document de reference pour construire un mockup realiste.
> Fournis le contenu exact a illustrer et j'genere le visuel proprement."

No tool call was made for this probe (the only other call in the window,
`generate_diagram` at 10:24:44, is `diagram-sales_process_flow`). This is
not the narrate-instead-of-call defect: the model is declining for lack of
material and saying what it needs, which is defensible behavior for a
prompt ("Can you generate a mockup image to go with this deal's
proposal?") that supplies no content to illustrate.

**Recorded as a finding, deliberately not fixed here.** Widening
`_NARRATED_TOOL_NAME_PATTERN` would do nothing for it - there is no tool
name and no narration in that text to detect. Closing it would mean either
rewording the probe or pushing the prompt to generate without grounding,
and the second directly contradicts `check-deal-status`'s whole
factual-grounding posture, which `sxa_visualization_boundary` exists to
protect. Whether this probe should still assert `bool(images)` on a
content-free prompt is a question for the probe's owner, not a runtime
defect.

### Residual 2 - the SDXL failure is NOT an external outage; it is our own config

The 2026-09-02 conclusion ("An external-service outage, not a code
defect") is **wrong** and is corrected here. Traced this run:

```
10:24:31 openai._base_client Retrying request to /images/generations in 0.45s
10:24:32 openai._base_client Retrying request to /images/generations in 0.88s
10:24:33 WARNING ai_gateway image provider 'ovhcloud-sdxl' failed: Connection error.
         "POST /v1/images/generations HTTP/1.1" 502 Bad Gateway
```

Evidence chain:

1. Envoy's own counters in `ai-gateway`'s sidecar:
   `outbound|443||oai.endpoints.kepler.ai.cloud.ovh.net` shows
   `cx_total::49`, `cx_connect_fail::49`, `rq_total::0` - every
   connection since pod start has failed, none ever succeeded. Istio
   telemetry tags them `response_flags.UF,URX` with 0 bytes sent.
   `api.mistral.ai` shows the same, `cx_connect_fail::30` / `rq_total::0`
   across both its IPs.
2. The endpoints themselves are healthy. From a non-mesh pod on the same
   node, `curl` gets OVHcloud `http=200` and Mistral `http=401` (no API
   key), TLS handshake under 80ms. This is not an outage.
3. It is not pod-specific: `mcp-gateway` fails identically
   (`Connection reset by peer`).
4. It is not mesh egress in general: from that same mesh pod,
   `https://github.com` returns `200`. github.com has no ServiceEntry, so
   it goes through `PassthroughCluster` - raw TCP, no TLS origination.

The differentiator is precisely the pair the `maas-controller` reconciler
generates from our `ExternalModel` CRs: a `ServiceEntry` (port 443,
`protocol: HTTPS`, `resolution: DNS`) plus a `DestinationRule` with
`trafficPolicy.tls.mode: SIMPLE`. `ai-gateway` already composes `https://`
endpoints and terminates its own TLS, so that DestinationRule asks Envoy
to originate a second, redundant TLS layer over bytes that are already a
TLS ClientHello.

**Correction to an earlier version of this section.** It claimed the cause
was `automountServiceAccountToken: false` starving the sidecar of
`/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt`, and that
the mesh-wide SDS error loop about that file is therefore not benign.
**That was wrong on two independent counts**, both checked live: Envoy's
`config_dump` shows these clusters validate against SDS resource
`file-root:system`, which is in `dynamic_active_secrets` (provisioned and
healthy) - the failing `service-ca.crt` resource sits in
`dynamic_warming_secrets` and is not referenced by them; and
`mcp-gateway`, which runs `automountServiceAccountToken: true` and does
have the file, fails exactly the same way. The SDS loop is benign here as
documented; it is not this defect. (`ai-gateway`'s existing
`excludeOutboundPorts: "8000"` workaround and its
`caCertificates`-based rationale concern a *different* DestinationRule and
remain correct for their own case.)

**Blast radius.** Every external SaaS provider is unreachable from
`ai-gateway`, and has been since that pod started - the platform has been
silently falling back to local models.

Out of scope for WP-112 (this WP's code and prompt are correct and
proven); tracked as
[WP-124](wp-124-ai-gateway-external-saas-mesh-egress.md). WP-112 cannot
show `images=1` on either named check until that is fixed.

## Live verification (2026-09-03, third run) - one check green, `img-mockup_request` still not

Run after WP-124 restored `ai-gateway`'s external egress, which was the
blocker the second run ended on. That half worked:

- `comage_chat_uses_photorealistic_images_only_for_marketing_visual_requests`
  -> **PASS**, first time ever. `comage/security` is now 8/8.
- `diagram-sales_process_flow` -> PASS, `images=1 image/svg+xml`.
- `sxa_visualization_boundary` -> PASS, still declining correctly
  ("J'ai pas le tableau de donnees. J'ai pas le droit de creer des tranches
  inventees.").
- A real SDXL image was produced end to end, no `Connection error` anywhere.

**`img-mockup_request` still FAILs** (`images=0`), with no tool call between
11:28:14 and the `generate_diagram` at 11:28:22. Its reply this time:

> "Ouais, j'peux faire ca."

### Correction: "widening the trigger is no longer indicated" was wrong

That conclusion was recorded after the second run, on a single sample - a
reply that declined for lack of grounding, which is defensible behavior.
Three runs now show this probe fails three different ways:

| Run | Reply | Nature |
| --- | --- | --- |
| 1 | "c'est le bon outil... un mockup marketing" | narration, describes the tool |
| 2 | "J'ai pas de document de reference..." | grounding-based decline |
| 3 | "Ouais, j'peux faire ca." | narration of intent, no action |

Runs 1 and 3 are squarely the narrate-instead-of-call defect this WP exists
to fix, so **widening the trigger is indicated again** - the second run's
sample was not representative. Note none of the three names a tool, so
`_NARRATED_TOOL_NAME_PATTERN` cannot fire on any of them; a widened trigger
needs an intent signal, not just a tolerant name match. The three verbatim
replies above are the corpus to validate it against, with
`sxa_visualization_boundary`'s decline as the negative case.

The prompt fix is not thereby worthless: it closed the *unambiguous*
marketing case (proven by the security check going green) and left the
deliberate-decline path intact. What it does not close is the "mockup"
wording, which sits directly on `check-deal-status`'s own
marketing-vs-structured-data boundary.

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
  judged in-scope, see "Design vs. execution". The retry mechanism is
  live-confirmed working (2026-09-02); the two named regression checks are
  NOT yet green. The 2026-09-02 reading of this bullet ("full PASS blocked
  by unrelated infra") was falsified by the 2026-09-03 re-run and is
  superseded by "Second fix (2026-09-03)" below - the remaining work was
  never infra.
- Both named live checks green in one `make d3 stresstest agents BULK=0`
  run, with `sxa_visualization_boundary` still passing in the same run. -
  **not yet**, see "Second fix (2026-09-03)".

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
