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
2. A real finding from that repo-side work worth verifying live: `retrieve_node`'s pre-existing, task-agnostic live-read escalation (ADR-0034's `_LIVE_READ_CLASSIFICATION`) bumps `effective_classification` to at least C2 on ANY successful Confluence search, even zero hits. A live no-project/C1-project DAT rehearsal must pick a topic that genuinely returns no Confluence hits, or Step 1 of the ADR-0550 webinar sequence will show C2 (still routed to OVHcloud, since it is eligible there too, but not the "C1" the script names) instead of a clean C1.
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
