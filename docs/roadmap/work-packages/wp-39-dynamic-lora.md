# WP-39: Dynamic LoRA adapter loading (promotes ADR-0303)

- **State:** Not started
- **ADRs:** ADR-0303 (Proposed -> To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-34 (merged + GPU run done)
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root. Refresh
> against the merged WP-34 state before starting.

## Goal

Promote stub ADR-0303, then move adapter selection from
deployment-time-static (ADR-0301's scope) to per-request dynamic: the AI
Gateway selects an approved adapter for the request's agent/task from
configuration, subject to classification routing.

## ADR references

Stub (verbatim, from `docs/adr/0300-v0.3-roadmap.md`): "Share base models
while selecting approved task/agent adapters dynamically."

Boundaries: ADR-0301 split off dynamic selection so it could be
delayed/rejected without unwinding 0301's serving mechanism; ADR-0304/WP-40
owns *policy-optimized* choice — this WP is mechanism only (declared
adapter per agent/task honored per request), not optimization.

## Preconditions

- WP-34 done through its GPU run (at least one real adapter registered and
  served statically).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `gitops/charts/models/values.yaml` (`loraAdapters` from WP-34),
  vLLM multi-LoRA request semantics (model parameter selects the adapter
  module), `components/ai-gateway/app/` (model-selection path),
  `policies/model-routing/`.

## Step 0 — ADR promotion

1. Create `docs/adr/0303-support-dynamic-lora-adapter-loading.md`
   (standard header, `- **Status:** To be implemented`, Target `v0.3`).
   Decision: promotion sentence + stub text, then: "The AI Gateway resolves
   the serving target per request: an agent/task whose model-routing policy
   declares an approved adapter is routed to that adapter module on the
   shared vLLM runtime (vLLM multi-LoRA request-level selection); requests
   without a declared adapter use the base model. Adapter approval remains
   a reviewed GitOps change (ADR-0302's promotion rule); a C2/C3-classified
   adapter is only selectable on serving paths already authorized for that
   classification (ADR-0021/0034). Selection is recorded in traces and
   usage metering." Standard-clauses pointer + Related ADRs (0021, 0034,
   0301, 0302, 0304).
2. `docs/adr/0300-v0.3-roadmap.md`: KEEP heading; body →
   `Promoted to a full decision record: see [ADR-0303](0303-support-dynamic-lora-adapter-loading.md) (WP-39 implementation).`
3. `docs/adr/README.md`: direct link + `To be implemented`.
4. `python3 platform/docs/check_docs.py` exits 0.

## Repo changes

1. Model-routing policy: per-agent/task `adapter:` declaration in
   `policies/model-routing/` following its existing structure.
2. AI Gateway: resolve adapter per request; classification guard
   (security-negative test: C2/C3 adapter never selected onto an
   external-eligible path); trace + metering attribute.
3. Tests: declared adapter honored; undeclared → base model; unknown adapter
   name fails closed; classification guard.

## What NOT to touch

Standard list; plus: no autonomous adapter choice (WP-40/WP-42 territory);
`gitops/charts/models` serving mechanics from WP-34 stay as-is.

## Acceptance checks

- `python3 -m pytest components/ai-gateway/ -q`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

1. Operator: on the GPU cluster, send requests for an adapter-declared task
   and a base-model task; verify vLLM serves the right module and traces
   record it.

## Status updates (then re-run check_docs.py)

- After merge: ADR-0303 → `Partially implemented (request-level selection and guards merged; GPU verification pending)`;
  after operator verification → `Implemented - see \`components/ai-gateway/app/\`, \`policies/model-routing/\`.`;
  index row + tracker + MEMORY.md accordingly.

## Out of scope / deferred

- Quality/cost/latency-driven adapter choice (WP-40 / ADR-0304).
