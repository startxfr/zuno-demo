# WP-39: Dynamic LoRA adapter loading (promotes ADR-0303)

- **State:** Closed — deferred (2026-08-30 — ADR-0303 reclassified Superseded
  by ADR-0526 for the serving mechanism it depends on; no live candidate or
  roadmap-declared need for per-request multi-LoRA selection; resumes under a
  future ADR if a genuinely new, non-merged adapter and a real
  multi-adapter-sharing need arise — see ADR-0303's Evolution note). (History:
  2026-08-15 - repo work merged; GPU verification was the outstanding
  operator step at the time. Step 0 promoted ADR-0303 verbatim. New
  `policies/model-routing/model-routing-policy.yaml` (per-agent/task
  `adapter:` declarations, `adapters: []` by default - WP-34's GPU
  training run hasn't produced a real registered adapter yet, so
  activating an entry before one exists would route real requests to a
  model vLLM doesn't actually serve; a commented example shows the
  shape). Bakes into the ai-gateway image (`policies/` convention,
  matching `policies/knowledge/`/`policies/tools/` in their own
  services) rather than the mounted-ConfigMap pattern
  `platform/ai-gateway/provider-routing.yaml` uses - required changing
  `components/ai-gateway/Dockerfile`'s build context to repo-root
  (`.`, was `components/ai-gateway`), mirrored in both
  `.github/workflows/build-publish.yml`'s matrix entry and
  `ansible/roles/ai_gateway_build/tasks/build.yml`.
  `app/model_routing_policy.py` (`ModelRoutingPolicy.adapter_for(agent,
  task)`) fails closed per malformed entry, not per file - a bad entry is
  skipped and logged, every other valid one still loads. `app/main.py`
  gains an `X-Zuno-Agent` header (new) alongside the existing but
  previously-unused `X-Zuno-Task` (WP-39 is the first real sender of
  both - `components/agent-runtime/app/clients/model_router.py`'s
  `chat_model_for`/`invoke_with_fallback` gained `agent_name`/`task_name`
  params, threaded from `app/graph/nodes.py`'s `_make_reason_node` and
  `app/graph/arkos_nodes.py`'s own reason-equivalent node using each
  closure's already-bound `agent`/`task` objects - `app/memory.py`'s
  separate extraction call site deliberately left without them, since a
  generic post-turn fact-extraction utility call is not "this agent/
  task's declared model behavior" in the same sense). Classification
  guard (the WP's own signature security property, "a C2/C3 adapter
  never reaches an external-eligible serving path"): enforced INSIDE
  `app/providers.py:chat_model_for()` itself, not just by its caller's
  discipline - an adapter is dropped (logged, never applied) unless
  `candidate.kind == "local"` AND the request isn't routed via ADR-0114's
  MaaS transport either (combining dynamic adapter selection with
  MaaS-mediated serving is out of this WP's scope). Selection recorded in
  traces/metering: `app/telemetry.py:model_call_span()` gained an
  `adapter` param/`zuno.adapter` span attribute, and the `model` value
  passed to it (plus the response's own `model` field) is already the
  adapter's served name whenever one applied, not the base model name.
  Tests (this repo's own established plain-script convention, run via
  each component's `.venv` - the brief's own literal `pytest` acceptance
  command doesn't match how this repo actually runs Python tests
  anywhere else, so the real convention was followed instead):
  `components/ai-gateway/tests/test_model_routing_policy.py` (7 tests:
  declared/undeclared/malformed-entry/missing-file/reload/default-
  classification) and `tests/test_adapter_selection.py` (4 tests:
  declared adapter honored, undeclared -> base model, adapter never
  applied to a SaaS candidate, adapter never applied via MaaS) - all
  green, alongside the full pre-existing ai-gateway and agent-runtime
  suites (`test_cache_integration.py`'s background OTel exporter
  DNS-resolution noise is the same pre-existing, expected no-live-cluster
  gap this repo already documents elsewhere; its own 5 assertions pass,
  exit 0). `python3 platform/docs/check_docs.py` PASS.)
- **ADRs:** ADR-0303 (Partially implemented -> Superseded by ADR-0526, 2026-08-30)
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
