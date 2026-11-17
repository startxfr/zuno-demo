# WP-292 fallback proof, live on demo333, 2026-11-17

Question: when Praxis's MaaS leg is unreachable, does its router fall back to
the direct KServe step? Answer, observed: **the router does try the direct
step, but a client gets no model answer.** The first call hangs until the
router deadline (504 after 601 s); later calls reach the direct step in about
10 s and get **HTTP 400**. After the revert everything is back on
`step="maas"`. Praxis's chart and config were not touched.

Run with the owner's named go in the session that ran it (Open WebUI call
included). Times are UTC. Persona: `consultant-01` (token read into memory
by `evaluations/golden_path_probe.py` `Context().persona_token`, never
printed); Open WebUI call as `eval-consultant-01` through Keycloak, as the
golden-path probe does.

## Method

One script (`run.sh` + `calls.py`, in the session scratchpad, not
committed) with a `trap` that deletes the ANP on any exit:

1. `oc get adminnetworkpolicy`: none exist.
2. `oc port-forward -n zuno-ai-gateways svc/praxis 18080:8080`.
3. Baseline: chat `gpt-oss-20b`.
4. `oc apply` the ANP below; wait 15 s.
5. Blocked: chat `gpt-oss-20b`, chat `auto`, `POST /v1/messages` (model
   `auto`), then one call through Open WebUI model `praxis.gpt-oss-20b`.
   Client timeout 900 s (router `timeout_ms` is 600000).
6. `oc delete adminnetworkpolicy`, wait 15 s.
7. After: the same three Praxis calls. `oc get adminnetworkpolicy` again.

Every call sends `Reply with exactly: pong`.

## The ANP (one, temporary)

```yaml
apiVersion: policy.networking.k8s.io/v1alpha1
kind: AdminNetworkPolicy
metadata:
  name: wp292-praxis-maas-block-temp
  labels:
    zuno.io/temporary: "wp-292-fallback-proof"
spec:
  priority: 90
  subject:
    pods:
      namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: zuno-ai-gateways
      podSelector:
        matchLabels:
          app.kubernetes.io/name: praxis
  egress:
    - name: deny-maas-gateway
      action: Deny
      to:
        - pods:
            namespaceSelector:
              matchLabels:
                kubernetes.io/metadata.name: openshift-ingress
            podSelector:
              matchLabels:
                app.kubernetes.io/instance: maas-default-gateway
```

Created 21:23:48, deleted 21:34:39 (about 11 minutes up).

## Results

| Phase | Call | HTTP | served by | Latency | Praxis log (step, status) |
|---|---|---|---|---|---|
| baseline | chat gpt-oss-20b | 200 | gpt-oss-20b | 0.4 s | `maas` 200 |
| blocked | chat gpt-oss-20b | **504** | none | **601.1 s** | `maas` "sub-request deadline exceeded" 504, then "iterative_request_router: deadline exceeded iterations=1" |
| blocked | chat auto | **400** | none | 10.2 s | `maas` 502 (TLS handshake: connection reset by peer), then `direct` iteration=1 **400**, body 215 bytes |
| blocked | POST /v1/messages auto | **400** | none | 10.1 s | same pair: `maas` 502, `direct` 400 |
| blocked | Open WebUI praxis.gpt-oss-20b | **400** | none | 10.8 s | same pair |
| after revert | chat gpt-oss-20b | 200 | gpt-oss-20b | 0.4 s | `maas` 200 |
| after revert | chat auto | 200 | qwen3.6-27b-instruct | 6.6 s | `maas` 200 |
| after revert | POST /v1/messages auto | 200 | qwen3.6-27b-instruct | 9.1 s | `maas` 200 |

The 400 body starts `{"error":{"message":"1 validation error: ... Unsupported
Medi...` (the script kept 60 characters, so the rest of the message and the
exact cause are **not recorded**). The `direct` step returns 400 with
`body_bytes=215` in all four cases, so the fallback is reached but the
direct request is refused by the model side or by the request it builds.
Not investigated, as instructed.

Log lines (tokens none present; `http_request{...}` span removed):

```
21:34:06.764 WARN  filtered_subrequest{step="maas"}: ... error=sub-request deadline exceeded status=504
21:34:06.765 WARN  iterative_request_router: deadline exceeded iterations=1
21:34:06.765 WARN  request rejected by filter filter="iterative_request_router" status=504
21:34:17.921 WARN  step="maas" error=sub-request connect error: TLSHandshakeFailure ... Connection reset by peer (os error 104), SNI: maas-default-gateway-istio.openshift-ingress.svc.cluster.local
21:34:17.921 INFO  sub-request complete step="maas" iteration=0 status=502 body_bytes=0
21:34:17.935 INFO  sub-request complete step="direct" iteration=1 status=400 body_bytes=215
(the same three lines at 21:34:27 and 21:34:38 for the two following calls)
```

## Reading

- With the leg blocked the first request waited the whole router deadline
  (600 s) with no reset: a silent drop on a new connection. The later three
  were reset within 10 s. The difference between the first call and the
  following ones is observed, not explained (a pooled or already-open
  connection is a hypothesis, not tested).
- Result against the expectation "falls back": a 5xx-triggered fallback
  happens (502 then `direct`), but the client sees **400, not a model
  answer**, and the first call sees a **504 at the deadline with no
  fallback**.
- Open WebUI shows the same 400 for `praxis.gpt-oss-20b`.

## Side effect to know

Praxis was not usable for models behind MaaS for about 11 minutes. Other
requests reached Praxis during the window: the log shows a `step="anthropic"`
502 at 21:25:42, and two further `maas` 502 then `direct` 400 pairs at
21:26:06 and 21:26:41 that are not this script's calls. The Zuno ai-gateway
was not selected by the ANP. Persona quota spent: 7 short calls
(`consultant-01`) plus one Open WebUI call (`eval-consultant-01`), all
`max_tokens` 200 or default.

## Revert proof

- `oc delete adminnetworkpolicy wp292-praxis-maas-block-temp`: deleted
  21:34:39.
- Next calls (21:34:57, 21:35:03, 21:35:12): `step="maas"` status 200.
- `oc get adminnetworkpolicy` after the run: `No resources found`. No
  port-forward or script process left.
- The `trap` was not needed (the script ran to the end).
