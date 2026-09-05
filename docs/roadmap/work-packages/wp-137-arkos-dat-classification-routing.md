# WP-137: Make Arkos DAT routing project-classification driven

- **State:** Not started
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

## Out of scope

- Project CRUD/UI — already implemented.
- New C1/C2/C3 taxonomy.
- Dynamic global sovereign mode.
- MaaS `ExternalModel` repair — WP-125.
- New external provider credentials.
- Changes to Tekos/Comage Qwen pairing.

## Completion criteria

WP-137 is done when the automated suite and one live C1/C2 comparison prove that Arkos DAT's execution location changes because of project/effective classification, with C2/C3 externalization fail-closed.
