# WP-03: MaaS adapter prototype in the AI Gateway

- **State:** Done (2026-08-18 — the brief's decision-risk clause was exercised: the operator chose a superseding ADR over completing ADR-0114 as written. ADR-0118 records the outcome — the AI Gateway stays Zuno's policy router, the merged adapter stays default-off as the delegation seam, and the keep-vs-delegate/cutover decision moves wholly to ADR-0201/WP-27, where the MaaS surface is actually being live-verified. Facts that drove it: the GPU-capacity gap is resolved (3rd GPU node, qwen25-7b-instruct-maas-backend Ready per ADR-0201's 2026-08-18 part-1 note) but the authenticated end-to-end MaaS request is blocked by an upstream RHOAI 3.5 EA2 mTLS defect in the MaaS payload-processing pipeline (part-2 note) — an upstream product dependency no v0.1 record should gate on. Prior state for the record: Operator pending (2026-08-14 — repo work merged: adapter, chart wiring, tests, coverage doc; awaiting live MaaS comparison per the Operator/human follow-up section below. Re-verified 2026-08-17: repo acceptance checks re-run clean (`py_compile`, `pytest components/ai-gateway/` 58/58, `helm lint`, coverage doc present, `check_docs.py`). `maasAdapter.enabled` correctly stays `false`. Live comparison still blocked - not by a WP-03-side gap but by ADR-0201's own documented architecture/capacity blocker: this cluster has exactly one GPU node and its only `nvidia.com/gpu` is already committed to the existing local models, so the MaaS-published `qwen25-7b-instruct-maas-backend` LLMInferenceService this WP would compare against can't schedule (`FailedScheduling: Insufficient nvidia.com/gpu`). Resolving that is a real infrastructure/cost decision (add a GPU node) that belongs to ADR-0201/WP-27, not this WP - nothing further to attempt here until it lands.))
- **ADRs:** ADR-0114 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** WP-27
- **Estimated files touched:** ~6

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR sections before editing. If the repository state contradicts
> a step, stop and report instead of improvising.
>
> **Decision risk:** ADR-0114 mandates prototype-then-compare. The coverage
> comparison may conclude that parts of the decision need a superseding ADR
> instead of completing ADR-0114 as written. If so, report that conclusion —
> do not silently change direction.

## Goal

Prototype an OpenShift AI MaaS adapter behind the AI Gateway's existing
OpenAI-compatible model client, and produce the feature-coverage comparison
ADR-0114 requires before any current gateway capability is removed. Zuno
keeps the business/context decisions (C1/C2/C3, sovereignty, task
requirements, quality tier, cost objective); MaaS becomes the model access
plane behind it.

## ADR references

Primary: [docs/adr/0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md](../../adr/0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md)

Consequence: a stable adapter keeps Agent Runtime decoupled from changing MaaS APIs during EA/TP. Security: Zuno's classification/source restrictions remain the stricter outer policy — MaaS authorization is never sufficient permission to externalize C2/C3 data.

Acceptance criteria: Standard clauses (docs/adr/README.md#standard-clauses) —
merged via review, docs updated, component tests demonstrate the behavior,
security-negative tests because the model-egress trust boundary is involved.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- Read fully before editing: everything under `components/ai-gateway/app/`
  (locate the OpenAI-compatible model client, the provider routing/fallback
  logic, and the C1/C2/C3 eligibility checks), plus
  `policies/model-routing/` and `gitops/charts/ai-gateway/values.yaml`.

## Repo changes (step by step)

1. **Adapter module:** add a MaaS provider adapter in
   `components/ai-gateway/app/` implementing the same interface as the
   existing provider client(s) you found (mirror the existing provider
   abstraction — do not invent a new one). The adapter targets the MaaS
   OpenAI-compatible gateway endpoint; endpoint and credentials come from
   configuration/External Secrets, never source.
2. **Selection stays with Zuno:** routing decisions (classification,
   sovereignty, eligibility) execute exactly as today, before the adapter is
   chosen. The adapter is selectable via configuration
   (`gitops/charts/ai-gateway/values.yaml`), default **off**, so the current
   path remains the default until the operator comparison completes.
3. **Security-negative tests:** prove a C2/C3-classified request refused for
   external egress today is *still refused* when the MaaS adapter is active
   (MaaS authorization must never widen Zuno policy).
4. **Coverage comparison doc:** create
   `docs/roadmap/evidence/adr-0114-maas-coverage.md` — a table of current
   gateway capabilities (routing, fallback, quotas/budgets plans, streaming,
   usage metering) vs. what MaaS provides, each row marked
   `keep-in-zuno | delegate-to-maas | verify-on-cluster`. Fill what is
   provable from code/docs; leave `verify-on-cluster` rows for the operator.
5. **Unit tests:** adapter request/response mapping, streaming pass-through,
   and error propagation, mocked — no live MaaS in CI.

## What NOT to touch

- Decision text of any existing ADR.
- The uncommitted ADR-0344 change set if still present in `git status`.
- Do **not** remove or bypass any existing gateway capability in this WP —
  removal is only allowed after the operator comparison is complete.
- `gitops/apps/*` `targetRevision`; chart `image.tag` policy (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m py_compile` on every touched file under `components/ai-gateway/app/`
- `python3 -m pytest components/ai-gateway/ -q` (if a tests dir exists; otherwise add one mirroring `components/rag-service/tests/` style)
- `helm lint gitops/charts/ai-gateway`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`
- `test -f docs/roadmap/evidence/adr-0114-maas-coverage.md`

## Operator / human follow-up (not executable by the model)

1. Operator: enable the adapter flag against a live OpenShift AI MaaS
   (needs ADR-0201 cluster prerequisites), run a full Agent Runtime request
   through Zuno routing + MaaS, and fill the `verify-on-cluster` rows of the
   coverage doc.
2. Operator + user: decide per capability keep-vs-delegate. If the decision
   materially changes ADR-0114's direction, open a superseding ADR instead
   of editing it.

## Status updates (then re-run check_docs.py)

- After repo merge: ADR-0114 body `- **Status:**` →
  `Partially implemented (adapter prototype and coverage comparison merged; live MaaS validation pending)`;
  index row → `Partially implemented`; tracker + this file's State.
- After operator validation and cutover decision: ADR-0114 →
  `Implemented - see \`components/ai-gateway/app/\`.` (or superseded — see
  decision risk); index row to match; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- MaaS governance objects (MaaSModelRef/Subscription/AuthPolicy) — WP-27 / ADR-0201.
- Removing current gateway capabilities (post-comparison only).
