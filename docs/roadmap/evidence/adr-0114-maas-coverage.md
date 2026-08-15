# ADR-0114 MaaS feature-coverage comparison

Tracks the "prototype the MaaS adapter behind the existing OpenAI-compatible
model client and compare feature coverage before removing current gateway
capabilities" operational requirement in
[ADR-0114](../../adr/0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md).
Owned by WP-03 (repo prototype) and closed out by WP-27 (live governance
verification) — see the
[implementation roadmap](../v0.1-v0.3-implementation-roadmap.md).

Each row is marked `keep-in-zuno` (Zuno retains this responsibility
regardless of MaaS), `delegate-to-maas` (MaaS is expected to take this over
once verified), or `verify-on-cluster` (cannot be proven from the repository
— needs a live OpenShift AI MaaS environment).

| Current `components/ai-gateway` capability | Status | Notes |
|---|---|---|
| Classification eligibility (C1/C2/C3 routing, `app/routing.py`) | `keep-in-zuno` | MaaS authorization is never sufficient to externalize C2/C3 data — proven by `test_maas_adapter_never_widens_c3_local_only_eligibility` in [test_maas_adapter.py](../../../components/ai-gateway/tests/test_maas_adapter.py). |
| `X-Zuno-Local-Only` source-level restriction (ADR-0035) | `keep-in-zuno` | Independent of classification; unaffected by which transport reaches a candidate. |
| Provider fallback ordering (`_invoke_with_fallback`, `_stream_completion`) | `keep-in-zuno` | Zuno-specific fallback chain; MaaS's subscription/quota model governs model *access*, not candidate ordering. |
| OpenAI-compatible request/response contract (`app/schemas.py`) | `keep-in-zuno` | Agent Runtime depends on this shape (ADR-0009); unaffected by the adapter. |
| Direct model access to local KServe/vLLM predictor Services | `delegate-to-maas` (candidate) | MaaS's `modelsAsService` publishes local models through a governed gateway instead of a raw Service URL. The prototype (`components/ai-gateway/app/maas_adapter.py`) proves the transport swap is mechanically trivial (same `ChatOpenAI` client, different `base_url`) but not MaaS parity. |
| Group-based model access / subscriptions | `delegate-to-maas` (candidate) | Zuno has no equivalent today; `MaaSSubscription` is additive, not a replacement. |
| Usage/cost telemetry (`app/telemetry.py`, ADR-0029) | `verify-on-cluster` | WP-27 threaded `X-Zuno-Request-Id` end to end (agent-runtime → ai-gateway `model_call_span` →, when routed via MaaS, `maas_adapter.chat_model_via_maas`'s own request header) so correlation is now *possible*; whether MaaS's own usage/token metrics actually surface that header back needs a live MaaS environment to confirm. |
| External-provider (OpenAI/Gemini/Anthropic/Mistral) direct API access | `keep-in-zuno` (for now) | No `via_maas: true` entry ships in `platform/ai-gateway/provider-routing.yaml` yet. WP-27 added a dedicated `MAAS_EXTERNAL_EGRESS_ENABLED` gate (default off, independent of `MAAS_ADAPTER_ENABLED`) so external egress through MaaS stays blocked even once a provider entry opts in, until the operator+user decide the lifecycle is acceptable (ADR-0201 acceptance criterion). |
| Streaming (SSE) behavior | `verify-on-cluster` | The adapter reuses `ChatOpenAI.astream`; needs a live MaaS endpoint to confirm SSE compatibility end to end. |
| API-key lifecycle for programmatic clients | `verify-on-cluster` | WP-27 wired the missing half: `gitops/charts/ai-gateway/templates/externalsecret-maas.yaml` resolves a Vault-seeded key (`ansible/roles/vault/tasks/install.yml`, path `maas/gateway-api-key`) into the `llm-provider-maas` Secret the adapter already read from. Minting/rotating the real key via MaaS itself (no such flow exists in this repo) and confirming the browser path never receives one remain live-cluster steps. |

## What the repo prototype proves today

- The transport swap is additive and reversible: no `provider-routing.yaml`
  entry opts in by default, and the global `maasAdapter.enabled` chart value
  defaults to `false` — enabling either alone changes nothing (both gates
  must be true).
- Enabling the adapter cannot widen classification eligibility: eligibility
  filtering (`RoutingTable.candidates_for`) runs entirely before the adapter
  is ever consulted.
- A misconfigured adapter (enabled without an endpoint) fails loudly
  (`MaasAdapterError`), not silently.

## What remains for the operator (WP-03 / WP-27)

Fill in the `verify-on-cluster` rows above against a live OpenShift AI 3.5
MaaS environment, then decide per capability whether to flip a provider's
`via_maas` field. If the comparison concludes MaaS should become the
default transport for local models, that is a direction change requiring a
superseding ADR — not an edit to ADR-0114's Decision text.
