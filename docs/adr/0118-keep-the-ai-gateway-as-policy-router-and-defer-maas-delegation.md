# ADR-0118: Keep the AI Gateway as policy router and defer MaaS delegation to the governance plane

- **Status:** Implemented - see `components/ai-gateway/app/maas_adapter.py` (merged, default-off) and `docs/roadmap/evidence/adr-0114-maas-coverage.md`; this record itself carries no further repo work.
- **Target:** v0.1
- **Date:** 2026-08-18
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md) for the v0.1 cutover decision and its compare-then-delegate completion path

## Context

ADR-0114 (v0.1) decided to evolve the AI Gateway into a policy router in
front of OpenShift AI MaaS: Zuno keeps the business-aware decisions
(C1/C2/C3, sovereignty, task requirements, quality tier, cost objective),
MaaS takes model access, subscription/quota enforcement and provider
publication. Its own operational clause mandated prototype-then-compare
before removing any gateway capability, and the WP-03 brief carried an
explicit decision risk: the comparison may conclude that a superseding
ADR is needed rather than completing ADR-0114 as written.

The prototype and comparison were delivered (roadmap WP-03):
`components/ai-gateway/app/maas_adapter.py` behind the existing provider
abstraction, `maasAdapter.enabled: false`, security-negative tests
proving C2/C3 refusals hold with the adapter active, and the
per-capability coverage table in
`docs/roadmap/evidence/adr-0114-maas-coverage.md`. The live half of the
comparison could not complete inside v0.1, for reasons outside this
repository (recorded in ADR-0201's dated notes):

1. The MaaS backend model itself is now live
   (`qwen25-7b-instruct-maas-backend`, `LLMInferenceService`,
   `Ready=True` on a third GPU node, 2026-08-18) - the earlier
   GPU-capacity gap is resolved.
2. The authenticated end-to-end request through the MaaS gateway is
   blocked by a platform-level mTLS defect in RHOAI 3.5 EA2's own MaaS
   payload-processing pipeline - an upstream product defect, not a Zuno
   gap; ADR-0201 records the reproduction and the upstream-filing
   option.

Meanwhile the entire MaaS integration surface ADR-0114 wanted to
delegate to (publication, subscriptions, `MaaSAuthPolicy`, usage
controls) is being delivered and live-verified under ADR-0201 (v0.2,
roadmap WP-27) - the governance plane, not the v0.1 gateway stream, is
where the delegation decision actually lands.

## Decision

Supersede ADR-0114's v0.1 completion path:

- The AI Gateway **remains Zuno's policy router with its own provider
  abstraction** for v0.1. No gateway capability is removed on the
  strength of the coverage comparison.
- The MaaS adapter prototype **stays merged and default-off**
  (`maasAdapter.enabled: false`) as the delegation-ready seam; the
  coverage table remains the baseline input for any future
  keep-vs-delegate decision.
- The per-capability keep-vs-delegate decisions and any cutover move
  **wholly into ADR-0201's scope (WP-27)**, to be taken only once the
  upstream RHOAI MaaS payload-processing defect is fixed and the
  authenticated end-to-end path is proven live. If that decision
  materially changes direction again, it takes a further superseding
  ADR under the v0.2 stream, not an edit.

ADR-0114's architectural intent - Zuno differentiates on
business/context policy instead of duplicating the model access plane -
is not reversed; what is superseded is the claim that v0.1 completes a
compare-then-delegate cutover. Tying a v0.1 record's closure to an
upstream product-maturity dependency misstated the risk; the honest
shape is a closed v0.1 record (prototype + comparison delivered, router
kept) and an open v0.2 governance record (ADR-0201) owning the live
verification and the delegation decision.

## Consequences

- The v0.1 stream closes without waiting on the upstream RHOAI defect.
- WP-27 inherits a single, complete decision surface: live MaaS
  verification, coverage-table `verify-on-cluster` rows, and the
  keep-vs-delegate call per capability.
- The adapter code path stays exercised by its mocked unit tests and
  security-negative suite so the seam does not rot while default-off.

## Security considerations

Unchanged from ADR-0114, and restated because they bind WP-27 too: Zuno
classification/source restrictions always remain the stricter outer
policy; MaaS authorization is never treated as sufficient permission to
externalize C2/C3 data. The default-off adapter keeps today's refusal
behavior byte-identical (proven by the WP-03 security-negative tests).

## Operational considerations

`maasAdapter.enabled` stays `false` until WP-27's live verification
passes. The coverage evidence doc is updated there, not here.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Implementation state, Acceptance criteria and Review
evidence.

## Related ADRs

- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md) (superseded)
- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md)
- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0020](0020-support-both-local-and-external-llm-providers.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0035](0035-prevent-restricted-internal-context-from-reaching-external-models.md)
