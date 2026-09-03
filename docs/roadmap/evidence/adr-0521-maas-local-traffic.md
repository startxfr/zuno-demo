# ADR-0521 MaaS local-traffic implementation evidence

Records the live-cluster proofs, discovered constraints, and recorded
decisions behind
[ADR-0521](../../adr/0521-route-local-model-traffic-through-maas.md)
(route ai-gateway's local model traffic through MaaS). Owned by WP-076 —
see the [implementation roadmap](../implementation-roadmap.md).
All live verification was performed 2026-08-25/26 against
`demo222.startx.fr` (OpenShift AI 3.5 EA2, MaaS `models-as-a-service`
tenant, `maas-default-gateway` in `openshift-ingress`).

## Outcome summary

Both local models (`qwen3.6-27b-instruct`, `gpt-oss-20b`) serve through
the MaaS gateway with full governance (kubernetesTokenReview auth,
per-subscription `TokenRateLimitPolicy`, ipp usage metering) and answer
10/10 consecutive completions each with full bodies. ai-gateway's real
request path selects the MaaS transport first (`zuno_provider:
local-maas` / `local-gpt-oss-maas`) and falls back to the same model's
direct Service on any MaaS failure. Measured MaaS overhead: **+46ms
median** (304ms vs 258ms direct, gpt-oss-20b, ~15-token completions,
in-cluster client).

## Per-item evidence against the ADR's decision items

| ADR item | Outcome | Evidence / notes |
|---|---|---|
| 1. API-key issuance flow | **Bypassed, not solved** | No working issuance endpoint exists on this MaaS build (`/v1/api-keys` 500s; only `/internal/v1/api-keys/validate` responds). ai-gateway authenticates with its own projected ServiceAccount token instead (`MAAS_SA_TOKEN_PATH`, audience `https://kubernetes.default.svc`, kubelet-rotated, read per call) via `MaaSAuthPolicy` subjects `system:serviceaccount:zuno-ai-run:ai-gateway`. The API-key path stays wired as documented fallback (`MAAS_GATEWAY_API_KEY_ENV`). |
| 2. Vault-seeded key | Deferred with item 1 | `gitops/charts/ai-gateway/templates/externalsecret-maas.yaml` now gates on `maasAdapter.apiKeyEnabled` (operator's explicit "key is minted and seeded" signal) — rendering it against an unseeded Vault path wedged the whole ArgoCD app (live incident, 2026-08-26). |
| 3. Config-only enablement | Done | `maasAdapter.enabled: true` (chart) + `via_maas: true` per provider entry; either alone changes nothing. |
| 4. Internal gateway Service endpoint | Done, with a discovered constraint | The endpoint is per-model and path-prefixed (`https://maas-default-gateway-istio.openshift-ingress.svc/<ns>/<model>/v1`) — NOT one shared gateway URL. The path-prefixed form is the only proven-working route; the header-gated form 403s (identity mismatch documented in `gitops/charts/models/values.yaml`). TLS: the gateway's cert is issued by `openshift-service-serving-signer`, trusted via the same `LOCAL_GPT_OSS_CA_BUNDLE` the direct local candidates use. |
| 5. Generalize WP-27's manifests | Done | `gitops/charts/models` `maas.models[]` list renders the MaaSModelRef/MaaSSubscription/MaaSAuthPolicy triple per model; both `Active`/`Ready` live. Includes per-model `-ai-gateway` subscriptions (1,000,000 tokens/h, priority 100). |
| 6. Reuse existing fallback | Done, proven twice | See "Fallback proof" below. |
| 7. Latency comparison | Done | 6-sample A/B, same in-cluster client, same prompt/body: MaaS median 304ms / mean 339ms; direct median 258ms / mean 258ms. +46ms (~18%) median overhead for auth + rate-limit + usage metering. |
| 8. Trace correlation | Partially proven | `X-Zuno-Request-Id` observed (Envoy `ext_proc` trace on the gateway) being carried through the `ipp-pre` header mutation into the routed request — the header survives the MaaS hop into vLLM. Joining it inside MaaS's own usage records/Tempo traces is deferred to WP-079's tracing work. |
| 9. quota.py decision | **Recorded: keep both, complementary** | See "Recorded decisions" below. |

## The empty-body incident: two stacked upstream bugs

MaaS-routed completions returned `200` + correct headers + **empty body**
— first qwen-only, then (after qwen's route was re-created) both models.
Root-caused 2026-08-26 with Envoy `config_dump` + `ext_proc` trace
logging on the gateway pod:

1. **KServe×Istio HTTPRoute rule-name collision.** KServe generates
   identical rule names (`v1-chat-completions-path`, …) for every
   LLMInferenceService, and Istio keys the per-route ext_proc override
   that wires a route to its InferencePool's endpoint-picker (EPP) by
   rule name. On the shared `maas-default-gateway` (MaaS mandates route
   adoption there) one model's EPP captured the override on **every**
   route — all of gpt-oss-20b's routes pointed at
   `qwen36-27b-instruct-epp-service`. Proven by attaching a standalone
   route with a unique rule name: it received the correct model's EPP
   immediately.
2. **Envoy ext_proc response-path race.** Even a correctly-wired EPP
   drops the body whenever its response-headers reply reaches Envoy
   before the response body has propagated into the EPP's filter
   position: Envoy then takes the buffered-chunk path, forwards the body
   to the EPP and continues **without awaiting the echo** — and in
   `FULL_DUPLEX_STREAMED` mode the server owns the body, so the client
   gets nothing. Which side of the race a request lands on is decided by
   gateway↔EPP RTT: qwen's EPP pod sat on the gateway's own node
   (sub-ms reply — 0/8 even after a clean EPP pod restart), gpt-oss's on
   another node (8/8). An upstream Envoy/llm-d bug, not a configuration
   error.

**Fix shipped** (`e0c444d`, `63cbc3f`, `c2b09a9` — full inline analysis
in `gitops/charts/models/templates/_llmisvc-route.tpl`): the charts own
`spec.router.route.http.spec` with (a) model-prefixed unique rule names,
(b) every real-traffic rule backed by the plain workload Service — no
InferencePool backend means no EPP ext_proc in the response path at all
(the controller's own Service-backed catch-all rules were 6/6 reliable
while InferencePool rules were 0/6 on the same listener), and (c) one
inert `…-inference-pool-anchor` rule per model so the InferencePool
stays referenced (KServe gates `InferencePoolReady` on that; without it
the LLMISvc goes `Ready=False` and MaaSModelRef reports
`Unhealthy/BackendNotReady` despite healthy traffic).

**What is given up, and the alternative.** Service backends forgo llm-d
load-aware endpoint picking — worth exactly nothing at `replicas: 1`
(both models, MIG-constrained). When EPP scheduling is actually wanted
(multi-replica), the interim alternative is to revert the rules to
InferencePool backends AND pin the scheduler pod away from the gateway's
node (anti-affinity), which makes the EPP always lose the race — it
works, but reliability then depends on network latency staying above the
race window, so treat it as a stopgap until the upstream race is fixed.
Auth, `TokenRateLimitPolicy` and ipp usage metering are gateway/
listener-level and unaffected by the backend kind throughout.

## Fallback proof

- **Production incident evidence:** during the empty-body window, every
  MaaS-preferred request failed at the MaaS candidate (JSON decode of an
  empty body) and fell back to the same model's direct candidate —
  ai-gateway logs show continuous `provider 'local-gpt-oss-maas' failed
  ... trying next fallback` with zero user-visible errors over hours of
  traffic. Exactly the config-outcome fallback ADR-0521 item 6 called
  for; no new code ran.
- **Controlled deny drill (2026-08-26 02:02–02:04 UTC):** the
  `payload-processing` ext_proc backend (which the `ipp` filter requires
  with `failure_mode_allow: false`) was scaled to 0, hard-failing the
  entire MaaS gateway while direct model Services stayed untouched.
  Baseline 02:02:13: `zuno_provider: local-gpt-oss-maas`. During the
  outage (02:03:13–17): 3/3 requests returned `200` with correct content
  via **`local-gpt-oss`** (same model, direct transport) in ~2s each
  (including the failed MaaS attempt), with ai-gateway logging
  `provider 'local-gpt-oss-maas' failed ... trying next fallback: Error
  code: 500` per attempt. Restored 02:03:31; first post-restore request
  returned via `local-gpt-oss-maas` again — full recovery, no restart,
  no operator action beyond the scale-back.
  Method note: a default-deny NetworkPolicy on the payload-processing
  pods was tried first and did NOT bite (gateway→ext_proc gRPC rides the
  mesh in a way that evades L4 policy matching — the known
  port-exclusion/tunneling trap); scaling the backend to 0 is the
  reliable deny primitive for this drill.

## Recorded decisions

- **quota.py `TokenBudgetLedger`: kept, alongside MaaS's
  `TokenRateLimitPolicy` — complementary, not redundant.** The ledger
  enforces per-quota-class × persona/project budgets *before dispatch*
  and across **all** providers (SaaS included); TRLP enforces
  per-subscription token limits at the MaaS gateway for local models
  only. Removing the ledger would leave SaaS traffic unbudgeted;
  scoping it down would change behavior for existing quota classes with
  no benefit. Known limitation, noted not fixed here (out of WP-076
  scope, pre-existing): the streaming path never consumes the ledger
  (`app/main.py`'s `_stream_completion`), so ADR-0511 enforcement is
  effectively unmetered for the (always-streaming) agent-runtime caller.
- **LoRA adapters never ride MaaS.** An adapter id replaces the request
  body's `model` field, which the whole MaaS auth chain keys on
  (`ipp-pre` derives `X-Gateway-Model-Name` from it; no MaaSModelRef
  exists for adapter ids) — and `app/providers.py` silently drops the
  adapter on `via_maas` candidates. ai-gateway's candidate loops now
  skip `via_maas` candidates whenever an adapter declaration resolved,
  landing adapter traffic on the same model's direct sibling
  (`tests/test_maas_adapter_guard.py`).
- **Embeddings stay out of MaaS** (user-confirmed scope): MaaS's proven
  route forms are chat-completions-shaped.

## Live verification summary (2026-08-26)

- `MaaSModelRef`/`MaaSSubscription`/`MaaSAuthPolicy` triples `Ready`/
  `Active` for both models, including the `-ai-gateway` SA subscriptions.
- 10/10 full-bodied completions per model through
  `maas-default-gateway-istio` with the ai-gateway SA token.
- Real API path: `POST /v1/chat/completions` with a Keycloak persona
  token returns `zuno_provider: local-gpt-oss-maas` for a MaaS-preferred
  (agent, task) and correct content/usage; qwen's default path returns
  `zuno_provider: local-maas` since its provider entry landed.
- Latency A/B as in item 7 above.
