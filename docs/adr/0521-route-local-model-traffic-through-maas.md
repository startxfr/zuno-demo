# ADR-0521: Route ai-gateway's local model traffic through MaaS

- **Status:** Proposed
- **Target:** v0.5
- **Date:** 2026-08-25
- **Decision owners:** Zuno Demo architecture team

## Context

ADR-0114 decided Zuno would become a business/context policy router in
front of OpenShift AI MaaS rather than reimplement MaaS-native capabilities,
and its coverage evidence doc
(`docs/roadmap/evidence/adr-0114-maas-coverage.md`) explicitly deferred the
"should MaaS become the default transport for local models" question,
saying it "requires a superseding ADR — not an edit to ADR-0114's Decision
text" once the live comparison concluded.

WP-27/ADR-0201 has now discharged nearly every `verify-on-cluster` row in
that evidence doc: the MaaS governance plane (subscriptions, group-based
access, `TokenRateLimitPolicy` rate limiting) is proven live end to end for
`gpt-oss-20b`, using real personas across both subscribed groups plus a
denial case. Today, `ai-gateway` still calls every local model's Service
directly — `components/ai-gateway/app/maas_adapter.py` (the transport) and
`platform/ai-gateway/provider-routing.yaml`'s `via_maas` flag (the switch)
have existed since WP-03/ADR-0114's prototype phase, but no provider entry
sets `via_maas: true` and `maasAdapter.enabled` is `false`. The comparison
the evidence doc called for can now conclude.

Two rows the evidence doc already marks `delegate-to-maas (candidate)` are
capabilities Zuno has never built and would otherwise need to: group-based
model access/subscriptions, and API-key lifecycle for programmatic clients.
`components/ai-gateway/app/quota.py`'s `TokenBudgetLedger` is Zuno's own
token-budget metering, kept "because only the inference layer can meter
tokens" — the same layer MaaS's `TokenRateLimitPolicy` already occupies for
MaaS-routed models, not yet proven equivalent.

## Decision

Adopt MaaS as the access path for **all** local-model traffic from
`ai-gateway` — present and future models — not only external/programmatic
clients. This is the direction-change ADR-0114's evidence doc anticipated;
ADR-0114 itself (Zuno as the stricter outer policy) is unchanged.

Implementation sequence:

1. **Discover and document MaaS's real API-key issuance flow.** Only the
   validation side (`/internal/v1/api-keys/validate`) has been observed live;
   no issuance endpoint or CR has been found in this repo or on the live
   cluster. This is the one genuine unknown and must be resolved before
   anything else — either a `maas-api` public endpoint or an operator-only
   mechanism.
2. **Vault-seed the minted key** into the path `externalsecret-maas.yaml`/
   `llm-provider-maas` already expects (`ansible/roles/vault/tasks/install.yml`,
   `maas/gateway-api-key`) — this plumbing already exists and is idle.
3. **Enable the transport, per model, as configuration only.** Set
   `maasAdapter.enabled: true` (`gitops/charts/ai-gateway/values.yaml`) and
   `via_maas: true` + `maas_model_ref` on each local provider entry in
   `provider-routing.yaml` (starting with `local-gpt-oss`). No new adapter
   code is required — `maas_adapter.py` already implements this transport and
   was proven mechanically correct by the WP-03 prototype.
4. **Point the endpoint at the internal gateway Service**
   (`maas-default-gateway-istio.openshift-ingress.svc`), not the external
   route — the external hostname works (proven by WP-27) but needlessly
   hairpins every local call out through the OpenShift router and back.
5. **Generalize WP-27's manifest pattern to every local model.** Each local
   model needs its own `MaaSModelRef` + `MaaSSubscription` wiring, the
   NetworkPolicy allowance for `maas-default-gateway` → workload
   (`gitops/charts/models/templates/networkpolicy-gptoss.yaml`'s fix is the
   template), and the `--served-model-name` alias trick for its
   `LLMInferenceService` (KServe's generated launcher appends its own names
   after the chart's `args` via `$@`; vLLM's argparse takes the last
   occurrence of a repeated flag, so the chart's own flag must repeat every
   name, not just add one).
6. **Reuse the existing fallback mechanism, don't build a new one.**
   `app/main.py`'s `_invoke_with_fallback` already iterates
   `RoutingTable.candidates_for()`'s ordered candidate list, catching
   per-candidate failures and trying the next — this is Zuno's existing,
   `keep-in-zuno` fallback chain (evidence doc row 3), unrelated to MaaS.
   Keeping a direct-Service candidate entry alongside each `via_maas`
   candidate, ordered so MaaS is preferred, makes "MaaS unreachable → direct
   call" a configuration outcome of code that already exists — no new
   fallback code is needed. See Security considerations below for the
   governance-during-fallback tradeoff this implies.
7. **Publish a live latency comparison**, MaaS-routed vs. today's direct
   call, before calling any model's cutover complete — MaaS adds a real
   chain (ingress → Envoy/Kuadrant auth+OPA+rate-limit → EPP scheduler →
   vLLM) that a direct Service call does not pay.
8. **Verify `X-Zuno-Request-Id` trace correlation survives the extra hops** —
   WP-27 confirmed the header is set by `maas_adapter.py`, not that it
   reaches vLLM/Kuadrant's own logs or MaaS's usage metrics (evidence doc's
   `verify-on-cluster` telemetry row).
9. **Evaluate, do not mandate, retiring `quota.py`'s `TokenBudgetLedger`**
   for MaaS-routed models once `TokenRateLimitPolicy` is proven equivalent
   (window semantics, per-project scoping, precedence order per ADR-0511
   clause 2). External-provider traffic (OpenAI, Anthropic, Mistral, …) is
   not MaaS-fronted and keeps using `quota.py` regardless of this ADR's
   outcome.

## Consequences

Every local model gains group-based access control and platform-native rate
limiting without Zuno writing that code itself — the two capabilities the
ADR-0114 evidence doc already flagged as things "Zuno has no equivalent
today." In exchange, MaaS becomes a real dependency in the local-model
request path (mitigated by item 6's fallback) and every new local model
carries a small, now-templated but recurring cost of governance manifests
(item 5) rather than a bare `LLMInferenceService`.

## Security considerations

Item 6's fallback intentionally allows a request to reach a local model
directly, bypassing MaaS's group-subscription and rate-limit checks, when
MaaS/Kuadrant/Authorino is unreachable. This is accepted because Zuno's own
C1/C2/C3 classification (ADR-0021) and eligibility filtering
(`RoutingTable.candidates_for`) run **before** either candidate is ever
selected and are unaffected by which transport ultimately serves the
request — MaaS is additional, defense-in-depth governance on top of Zuno's
policy layer, not a substitute for it (unchanged from ADR-0201's own
framing: "Zuno the stricter outer policy"). A request that would have been
denied by Zuno's policy is denied identically whether or not it ever reaches
MaaS.

## Operational considerations

API-key rotation follows the existing manual pattern (re-seed Vault, re-run
`make d1 install vault` — same as every other provider key); MaaS does not
change this. The live latency comparison (item 7) should be re-run after any
change to the Kuadrant/Connectivity-Link chain, since that chain — not this
ADR's own manifests — determines most of the added-hop cost.

## Acceptance criteria

- Every local model in `provider-routing.yaml` has a corresponding
  `MaaSModelRef`/`MaaSSubscription`/`MaaSAuthPolicy` triple and passes the
  same positive/negative-group proof WP-27 established for `gpt-oss-20b`.
- `maasAdapter.enabled: true` and each local provider entry sets
  `via_maas: true`, pointed at the internal gateway Service.
- A documented live latency comparison (MaaS-routed vs. direct) exists for at
  least one model before that model is considered cut over.
- A live test demonstrates the fallback path: with MaaS deliberately made
  unreachable, a request still succeeds via the direct-Service candidate.
- `X-Zuno-Request-Id` is confirmed present in MaaS/Kuadrant/vLLM's own logs
  for a real routed request, not only at the adapter boundary.
- An explicit, recorded decision on `quota.py`'s `TokenBudgetLedger` (kept,
  scoped down to non-MaaS providers only, or removed) backed by a documented
  equivalence check against `TokenRateLimitPolicy`.

## References

- `docs/roadmap/evidence/adr-0114-maas-coverage.md` — the coverage comparison
  this ADR concludes.
- ADR-0201's final 2026-08-25 note — the live proof this ADR builds on.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md)
  — the origin decision this extends, not supersedes.
- [ADR-0201](0201-complete-the-openshift-ai-maas-governance-plane-integration.md)
  — the governance-plane implementation this depends on.
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md) —
  the classification layer this ADR's Security considerations rely on
  remaining unaffected.
- [ADR-0511](0511-define-okf-quota-policy-enforced-via-kuadrant.md) — the
  Kuadrant/`TokenRateLimitPolicy` mechanism item 9 evaluates against
  `quota.py`.
