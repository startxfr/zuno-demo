# MaaS front returned an instant 503 on every model: the Kuadrant wasm module never loaded (2026-10-24)

Read-only diagnosis on demo333 for WP-157 step 1, then one restart authorised by the user.

## Symptom

Every call through `maas-default-gateway-istio` (the ai-gateway's `*-maas` providers, 1858 errors and
zero success over 6 h) failed with an **empty 503 in 0.0 s** for `gpt-oss-20b`, `qwen35-9b` and
`qwen36-27b-instruct`. The direct providers worked, so users never noticed: the ai-gateway falls back on
each call. This is not load, queueing or the llm-d scheduler (the 2026-10-22 hypothesis).

## Cause

The Envoy of the gateway pod reported `wasm.remote_load_fetch_failures: 1`. Its start-up log
(2026-10-22 10:41:47Z) says `Wasm remote code fetch is unstable` then `Retry limit exceeded for
fetching data from remote data source`, during the same minute its CA requests were still failing.
Envoy never refetched: the Kuadrant wasm-shim (served at
`http://kuadrant-operator-wasm.openshift-operators.svc.cluster.local:8082/plugin.wasm`) stayed unloaded for
the 38 hours the pod ran, and with no filter the gateway answered 503 to everything. The Kuadrant objects
all said `Accepted/Enforced=True`; they do not prove the wasm loaded (see WP-54). Only the MaaS gateway
carries a wasm plugin (the data-science and zuno-agent gateways have none).

## Fix and result

Deleting the pod (one replica, no config change) made the new pod fetch the module at start-up:
`wasm.remote_load_fetch_successes: 1`, `fetch_failures: 0`. The same probe now gets
**HTTP 403 `no matching subscription found for user`** on the three models in 0.0 to 0.2 s: the front now
enforces its policies. The subscription `gpt-oss-20b-ai-gateway` has
`owner.users: [system:serviceaccount:zuno-ai-run:ai-gateway]`, which is the identity of the token used,
so the identity must have been derived differently; see the second fix below.

## Lessons

- A gateway pod that logs `Retry limit exceeded` for a wasm fetch at start-up is broken until restarted;
  check `wasm.remote_load_fetch_failures` in its Envoy stats (`pilot-agent request GET stats`) after any
  start-up where istiod or the CA was slow.
- Alert on `wasm.remote_load_fetch_failures > 0` for the MaaS gateway.

## Second fix: the identity is the path, so the MaaSModelRef takes the LLMInferenceService name

The live `maas-gateway-auth` is generation 14 (RHOAI 3.5.0 GA) and no longer has the `/llm/` branch of
`maas-llm-path-identity-off-by-one.md` (0 occurrences). It derives the model identity from the request path:
`segment[0]/segment[1]` when the path has at least two segments and the first is not `v1` or `maas-api`,
the `X-Gateway-Model-Name` header otherwise. The adopted KServe routes are `/zuno-ai-run/<llmisvc>/...`, so the
identity was `zuno-ai-run/gpt-oss-20b` while the refs, subscriptions and token-rate-limit policies were keyed
`zuno-ai-run/gpt-oss-20b-maas` (probes: the `-maas` path gives 404, a bare path with the header or body model
gives 404). Commit 7cc33489 names the four local MaaSModelRefs after their LLMInferenceService
(`gpt-oss-20b`, `qwen36-27b-instruct`, `qwen35-9b-wesh`, `qwen35-9b`), plus `maas_model_ref` in
`provider-routing.yaml` and `lightspeed-config`.

Result after the sync (probe as the ai-gateway ServiceAccount through `maas-default-gateway-istio`):
`gpt-oss-20b` 200 in 0.2 s; `qwen36-27b-instruct` 200 in 0.6 s, `qwen35-9b` 200 in 0.4 s,
`qwen35-9b-wesh` 200 in 0.3 s (body model = the served name, e.g. `qwen3.5-9b`; the llm-d router answers 404
for an unknown served name, which is not an auth problem). All subscriptions and MaaSAuthPolicies are Active
under the new names, the ArgoCD Applications `models`, `lightspeed-config` and `ai-gateway` are Synced and Healthy.

## Still open

The ai-gateway forwards the caller's Keycloak JWT to MaaS (`maas_adapter.py`), and the gateway's AuthPolicy
only authenticates Kubernetes TokenReview tokens and `sk-oai-` API keys, so user-token calls get HTTP 401
(logged as `provider 'local-maas' failed ... Error code: 401`, one 500) and the gateway falls back to the direct
provider. Making MaaS accept the Keycloak token (the externalOIDC / audience question) or sending the
ServiceAccount token for the MaaS hop is the remaining work of WP-157 step 1 and step 4.
