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
so the user string the AuthPolicy derives does not match: this is the open `model_identity`
path-versus-map-key defect (`maas-llm-path-identity-off-by-one.md`), now reachable because the wasm is loaded.

## Lessons

- A gateway pod that logs `Retry limit exceeded` for a wasm fetch at start-up is broken until restarted;
  check `wasm.remote_load_fetch_failures` in its Envoy stats (`pilot-agent request GET stats`) after any
  start-up where istiod or the CA was slow.
- Alert on `wasm.remote_load_fetch_failures > 0` for the MaaS gateway.
