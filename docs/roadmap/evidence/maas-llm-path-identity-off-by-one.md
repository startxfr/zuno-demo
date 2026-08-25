# RHOAI MaaS: the generated AuthPolicy's `/llm/` path branch extracts model identities off by one

Self-contained reproduction for an upstream report (Red Hat support case or the
OpenShift AI / Open Data Hub Models-as-a-Service component's tracker). Everything below
was captured live on 2026-08-25 against the versions stated; no speculation.

## Affected versions

| Component | Identifier |
|---|---|
| OpenShift AI Self-Managed | 3.5 EA2 (`platform.opendatahub.io/version: 3.5.0-ea.2`) |
| Operator CSV | `rhods-operator.3.5.0-ea.2` (beta channel, pinned `startingCSV`) |
| Generated object | `AuthPolicy/maas-gateway-auth` in `openshift-ingress`, labels `app.kubernetes.io/managed-by: maas-controller`, `generation: 1` (never hand-modified) |
| OpenShift | 4.22 |

## Summary

The MaaS controller generates one Kuadrant `AuthPolicy` for its gateway. Every place
that policy derives a model identity from the **request path** — the branch guarded by
`request.path.startsWith("/llm/")` — indexes the path segments without accounting for
the `/llm/` prefix segment itself, producing `llm/<namespace>` where the rest of MaaS
expects `<namespace>/<modelRef name>`. Consequence: any request arriving on an
`/llm/...` route fails subscription selection (and the OPA entitlement check) with
`no matching subscription found for user`, HTTP 403, regardless of the caller's real
entitlement.

The defect is currently **latent** on our cluster only because no HTTPRoute matches
`/llm/` — model traffic uses the bare `/<ns>/<model>/...` path rules plus the
`X-Gateway-Model-Name` header branch, which work. The moment anything publishes an
`/llm/`-prefixed route, that entry point is dead on arrival.

## The generated logic

The same extraction appears **six times** in the one generated `AuthPolicy` — five CEL
expressions and, independently reimplemented, the OPA Rego. All six index identically.

CEL (in `spec.defaults.rules.metadata.subscription-info.http.body.expression`,
three `authorization.*.cache.key.selector`s, and
`response.success.filters.identity.json.properties.selected_subscription_key`):

```cel
request.path.startsWith("/llm/")
  ? request.path.split("/").filter(x, x != "")[0] + "/" + request.path.split("/").filter(x, x != "")[1]
  : ("x-gateway-model-name" in request.headers ? request.headers["x-gateway-model-name"] : "")
```

Rego (in `spec.defaults.rules.authorization.require-group-membership.opa.rego`):

```rego
path_parts := [p | p := split(request_path, "/")[_]; p != ""]

path_model_identity := sprintf("%s/%s", [path_parts[0], path_parts[1]]) {
    count(path_parts) >= 2
}

model_identity := path_model_identity {
    startswith(request_path, "/llm/")
} else := header_model_identity { ... }
```

## Segment-by-segment

For `POST /llm/zuno-ai-run/gpt-oss-20b-maas/v1/chat/completions`:

```
split + filter  ->  ["llm", "zuno-ai-run", "gpt-oss-20b-maas", "v1", "chat", "completions"]
                       [0]        [1]              [2]
computed        ->  [0] + "/" + [1]  =  "llm/zuno-ai-run"
required        ->  [1] + "/" + [2]  =  "zuno-ai-run/gpt-oss-20b-maas"
```

The guard fires **only** on `/llm/`-prefixed paths, but the indices are the ones that
would be correct for the *unprefixed* `/​<ns>/<model>/...` form. Guard and indices
disagree by exactly one segment.

## Live proof that the computed value is rejected and the shifted value accepted

Direct calls to maas-api's own subscription selector (the endpoint the AuthPolicy's
`subscription-info` metadata step invokes), from an in-cluster pod, varying only
`requestedModel`:

```
POST https://maas-api.redhat-ods-applications.svc.cluster.local:8443/internal/v1/subscriptions/select
     {"groups":["agent_tekos"],"username":"consultant-01",
      "requestedSubscription":"","requestedModel":"<X>"}
```

| `requestedModel` | Response |
|---|---|
| `llm/zuno-ai-run` — what the expression computes | `{"phase":"","ready":false,"error":"not_found","message":"no matching subscription found for user"}` |
| `zuno-ai-run/gpt-oss-20b-maas` — what `[1]/[2]` would compute | `{"name":"gpt-oss-20b-tekos","namespace":"models-as-a-service","priority":10,...,"phase":"Active","ready":true}` |

The caller (`consultant-01`, group `agent_tekos`) holds an Active `MaaSSubscription`
for the model throughout — the failure is purely the identity string.

The Rego branch fails the same way independently: its `model_access` map is keyed
`{"zuno-ai-run/gpt-oss-20b-maas": {...}}`, so `model_identity = "llm/zuno-ai-run"`
looks up `null` and the deny-by-default rule rejects.

## Two self-consistent fixes (either resolves all six sites)

1. Keep the `/llm/` guard, shift the indices: `filtered[1] + "/" + filtered[2]`
   (Rego: `path_parts[1]`, `path_parts[2]`, guard `count >= 3`).
2. Keep the indices, change the guard to select the bare `/​<ns>/<model>/...` form —
   though that form currently reaches the header branch via the ipp-pre body-to-header
   ext_proc and works, so (1) is the smaller change.

## Impact assessment as observed

- Header-based and bare-path flows: unaffected and proven working end to end
  (real 200 completions for two differently-subscribed groups, 403 for an
  unsubscribed one, Limitador counters advancing).
- `/llm/` path flow: would fail 100% of requests with 403
  `no matching subscription found for user` — indistinguishable, from the caller's
  side, from a genuine entitlement denial, which makes it expensive to diagnose in the
  field (it cost us a full investigation pass to separate identity-resolution failures
  from real denials on the header form).

## Local mitigation in this repository (zuno-demo)

None possible or appropriate — the object is controller-generated and reconciled. We
carry a precheck tripwire (`ansible/roles/openshift_ai/tasks/precheck.yml`, runs on every `make d1 check openshift-ai`) that
raises a blocked-resource finding if an `/llm/` route ever appears while the live
policy still contains `[0]`-indexed extraction, pointing at this document.
