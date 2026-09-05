# WP-137: Make Arkos DAT routing project-classification driven

- **State:** Operator pending (2026-09-05 - repo-side mechanism complete: DAT baseline is project-derived (C1 default), reflect_node follows effective_classification instead of a fixed C2 ceiling, ai-gateway's new `local_only_for` policy field fail-closes C2/C3 to local providers, and the OKF authorization matrix regenerates clean. Automated tests 1, 2 (implied by 1's C1 code path), 3, 4, 5, 8, 9, 10 pass; tests 6/7 exercise pre-existing, unmodified mechanisms (`local_only_required`, provider-failure fallback) already covered elsewhere in the suite. The live C1/C2 comparison below is unrun.)
- **ADRs:** ADR-0550
- **Depends on:** ADR-0527 project classification, ADR-0034 effective classification, ADR-0416 OVH provider, existing `gpt-oss-20b` local serving
- **Estimated effort:** 1.5–2 days
- **Difficulty:** Medium

## Goal

Make Arkos `draft-architecture-testimonial` (DAT) select its reasoning model from the real project/effective classification:

```text
no project -> C1
project C1 -> C1 baseline
project C2 -> C2 baseline
project C3 -> C3 baseline
```

and route:

```text
C1    -> ovhcloud-gpt-oss-120b -> local-gpt-oss-20b fallback
C2/C3 -> local-gpt-oss-20b only
```

## Why this work is still required

The project object and classification are already implemented and already participate in the generic effective-classification mechanism. Do not rebuild project management.

The remaining gap is specific to Arkos DAT's historical classification/routing behavior, including the ADR-0416 fixed-C2 external reflection exception. The webinar requires the selected project's class to be observable in the actual DAT placement decision.

## Repo changes

### 1. DAT baseline classification

Update Arkos graph/runtime handling so `draft-architecture-testimonial` starts from:

- project classification if `project_id` is present and authorized;
- C1 otherwise.

Do not trust a caller-supplied classification independently of the authoritative project record already resolved by the runtime/BFF path.

### 2. Preserve monotonic escalation

Reuse the existing effective-classification rank/escalation helper.

All additional context remains capable of escalating the turn:

- technical RAG;
- project context;
- Confluence/MCP results;
- history/memory;
- any intermediate artifact carrying a stronger classification.

No step can downgrade the classification.

### 3. DAT-specific model order

Add/update the `arkos/draft-architecture-testimonial` routing entry so the effective candidate order implements:

```text
C1:
  1. ovhcloud-gpt-oss-120b
  2. local-gpt-oss(-maas/direct according to current supported local path)

C2/C3:
  1. local-gpt-oss(-maas/direct)
  2. no external survivor
```

The exact provider aliases must reuse the repository's current names; do not invent a parallel provider.

### 4. Remove the fixed-C2 DAT reflection exception

For the DAT task, stop applying ADR-0416's fixed C2 ceiling to `reflect_node`.

Use the current effective classification for DAT reflection/review calls.

Expected:

```text
C1 reflect    -> OVH permitted
C2/C3 reflect -> local only
```

Do not change unrelated Arkos tasks unless required by shared code and explicitly covered by tests.

### 5. Keep source restrictions stronger

`local_only_required` and source-level `external_model_policy.allow_context: false` must continue to remove external providers even for an otherwise C1/C2-eligible model.

### 6. OKF/documentation regeneration

Update the Arkos task/OKF model-routing documentation and regenerate authorization matrices using the existing generator/check path.

Do not hand-maintain a second routing truth in the frontend documentation.

## Tests

Add/adjust automated coverage for at least:

1. no project -> C1 -> OVH lead;
2. project C1 -> OVH lead;
3. project C2 -> local GPT-OSS only;
4. project C3 -> local GPT-OSS only;
5. C1 project + C2 retrieved context -> effective C2 -> local only;
6. C1 project + `local_only_required` -> local only;
7. OVH unavailable at C1 -> local GPT-OSS fallback;
8. local GPT-OSS unavailable at C2/C3 -> explicit failure, never external fallback;
9. classification never decreases after context accumulation;
10. unrelated Arkos tasks retain their pre-WP routing behavior unless the ADR explicitly changes them.

## Live verification

Use real frontend/BFF project creation/selection, not a synthetic direct header-only test.

Create or reuse demo projects:

```text
webinar-public       C1
webinar-confidential C2
webinar-restricted   C3
```

Run the same DAT prompt from C1 and C2 and record:

- effective classification;
- selected provider/model;
- request/trace id;
- local model serving evidence for the C2 path.

C3 may use a short smoke request if a full long-form generation would consume webinar rehearsal time unnecessarily.

## Operator / human follow-up (not executable by the model without explicit go-ahead)

1. Repo-side is complete: `components/agent-runtime/app/graph/arkos_nodes.py`'s DAT baseline/reflect changes, `components/ai-gateway`'s new `local_only_for` policy field, `policies/model-routing/model-routing-policy.yaml`'s tiered DAT entry, and the regenerated `agents/arkos/agent.okf.md` authorization matrix are all merged and covered by automated tests (`components/agent-runtime/tests/test_arkos_nodes.py`, `components/ai-gateway/tests/test_model_routing_policy.py`, `components/ai-gateway/tests/test_arkos_dat_classification_tiering.py`).
2. **Resolved 2026-09-05, live-caught rehearsing Step 1**: `retrieve_node`'s pre-existing, task-agnostic live-read escalation (ADR-0034's `_LIVE_READ_CLASSIFICATION`) used to bump `effective_classification` to at least C2 on ANY successful Confluence search, even zero hits - since every DAT turn declares `confluence.page.search` unconditionally, this made a clean C1 unreachable for any real DAT turn once Confluence was healthy (confirmed live: a no-project DAT request came back C2). Fixed to escalate only when Confluence actually returns matching pages, matching ADR-0034's own written text ("escalated ... when Confluence content enters context") - covered by `test_retrieve_node_dat_confluence_zero_hits_does_not_escalate`/`test_retrieve_node_dat_confluence_with_hits_still_escalates_to_c2` in `components/agent-runtime/tests/test_arkos_nodes.py`.
2b. **A second, compounding finding, same rehearsal session**: even after the fix above, WP-136's own suggested Step 1 prompt ("Draft a one-paragraph architecture summary for a public reference case about X") still came back C2, because it does not match any of `_extract_topic`'s `_TOPIC_PATTERN` forms in `arkos_nodes.py` (which require "dat"/"architecture testimonial"/"document" as the object noun - "architecture **summary**" doesn't match). `plan_node` then falls back to the WHOLE raw sentence as the Confluence search topic, and the generic framing words ("architecture", "summary", "reference", "case") matched real pages in this cluster's live Confluence instance regardless of the actual subject - confirmed by testing a deliberately unrelated topic ("renewable energy grid modernization") with the same boilerplate framing, which also came back C2. Fixed in `ansible/playbooks/demo_step_1.yml`'s suggested prompt ("Draft an architecture testimonial about X.", which does match `_TOPIC_PATTERN` and extracts a clean topic) - no agent-runtime code change needed for this half, since the extraction regex was already correct, only WP-136's own prompt wording was wrong. Re-verify live that Step 1's corrected prompt now shows a clean C1 before relying on it in the real webinar.
3. Operator: run the "Live verification" scenario above (real frontend/BFF, the three demo projects, C1 and C2 DAT prompts) and record effective classification, selected provider/model, request/trace id, and local-serving evidence for C2.
4. Once verified: this WP's tracker -> `Done`; contributes toward ADR-0550 `Status` -> `Implemented` once WP-135/WP-136 are verified too.

## Out of scope

- Project CRUD/UI — already implemented.
- New C1/C2/C3 taxonomy.
- Dynamic global sovereign mode.
- MaaS `ExternalModel` repair — WP-125.
- New external provider credentials.
- Changes to Tekos/Comage Qwen pairing.

## Completion criteria

WP-137 is done when the automated suite and one live C1/C2 comparison prove that Arkos DAT's execution location changes because of project/effective classification, with C2/C3 externalization fail-closed.
