# WP-292 fallback proof, re-run after 318e65e2, demo333, 2026-11-18

Re-run of [the 2026-11-17 proof](wp-292-fallback-live-2026-11-17.md) after the
two Praxis fixes of 318e65e2 (live since the pod restart; the ConfigMap
`praxis-config` was read before the run): the `direct` step sets
`content-type: application/json`, and the MaaS cluster carries
`total_connection_timeout_ms: 5000` and `read_timeout_ms: 180000`. Same
method, same ANP, same calls, same personas (`consultant-01` tokens read into
memory and never printed; Open WebUI as `eval-consultant-01`), prompt `Reply
with exactly: pong`. Run with the owner's named go in the session that ran
it. Times UTC. Praxis's chart and config were not touched.

**Result: with the MaaS leg blocked, all four calls get HTTP 200 with a model
answer from the direct step, none waits more than 14 s, and after the
revert the calls are back on `step="maas"`.** One difference from the
expectation: the baseline call returned 503 (see below).

## ANP

Identical to the 2026-11-17 manifest (`wp292-praxis-maas-block-temp`, Deny,
priority 90, subject the `app.kubernetes.io/name=praxis` pods of
`zuno-ai-gateways`, to the `app.kubernetes.io/instance=maas-default-gateway`
pods of `openshift-ingress`). Created 07:43:47, deleted 07:44:44 (57 s up).
`oc get adminnetworkpolicy` listed none before and after.

## Results

| Phase | Call | HTTP | served by | Latency | Praxis log (step, status) |
|---|---|---|---|---|---|
| baseline | chat gpt-oss-20b | **503** | none | 1.1 s | `token_rate_limit` fails closed, no routing step (see below) |
| blocked | chat gpt-oss-20b | 200 | gpt-oss-20b | 5.4 s | `maas` 502 (ConnectTimedout to 172.30.191.207:443), then `direct` 200 |
| blocked | chat auto | 200 | qwen3.6-27b-instruct | 12.5 s | `maas` 502 (TLS handshake failure), then `direct` 200 |
| blocked | POST /v1/messages auto | 200 | qwen3.6-27b-instruct | 14.1 s | `maas` 502 (ConnectTimedout), then `direct` 200 |
| blocked | Open WebUI praxis.gpt-oss-20b | 200 | gpt-oss-20b | 6.0 s | `maas` 502 (ConnectTimedout), then `direct` 200 |
| after revert | chat gpt-oss-20b | 200 | gpt-oss-20b | 0.5 s | `maas` 200 |
| after revert | chat auto | 200 | qwen3.6-27b-instruct | 10.9 s | `maas` 200 (answer text empty in the body, see below) |
| after revert | POST /v1/messages auto | 200 | qwen3.6-27b-instruct | 7.2 s | `maas` 200 |

Every blocked answer was `pong`. The first blocked call took 5.4 s: about 5 s
of connect bound plus the answer, as expected. Blocked-call log pairs
(`http_request{...}` span removed):

```
07:44:11.040 WARN  step="maas" error=sub-request connect error: ConnectTimedout ... connecting to server addr: 172.30.191.207:443
07:44:11.040 INFO  sub-request complete step="maas" iteration=0 status=502 body_bytes=0
07:44:11.274 INFO  sub-request complete step="direct" iteration=1 status=200 body_bytes=647
```

The same three-line pattern appears for the other three blocked calls
(07:44:16 TLS handshake failure; 07:44:28 and 07:44:43 ConnectTimedout), each
ending in `direct` 200 (body 1160, 1295 and 639 bytes). Compared with
2026-11-17 (504 after 601 s, then 400 "Unsupported Media Type"), both defects
are gone.

## Differences from the expectation, recorded as observed

1. **Baseline 503.** The first call, before the ANP, got HTTP 503 with an
   empty body after 1.1 s. The Praxis log shows
   `token_rate_limit accounting phase="reserve" ... backend="shared_kv"
   result="failed" error="unavailable"`, then `admission backend failed,
   failing closed`, then `request rejected by filter filter="token_rate_limit"
   status=503`. The Redis pod in `zuno-auth` was Running (4 d 11 h). It
   happened once in the previous 15 minutes of Praxis logs and the next calls
   all passed, so it looks like a first request after an idle period; it is
   **not investigated**. The baseline is therefore not a 200 `step="maas"`
   reference; the post-revert calls serve as the `maas` reference.
2. **Post-revert `chat auto` answer text empty.** HTTP 200, served by
   qwen3.6-27b-instruct in 10.9 s, `step="maas"` 200 (body 1441 bytes), but
   the script read no `content` (likely the model spent its 200 tokens on
   reasoning; the body was not kept). Not investigated.

## Side effect

For 57 s the MaaS-backed models answered through Praxis via the direct step.
Praxis's own calls plus any other client in that window were served directly.
The Zuno ai-gateway was not selected by the ANP. Quota spent: 7 short
`consultant-01` calls and one Open WebUI call (`eval-consultant-01`).

## Revert proof

- `oc delete adminnetworkpolicy wp292-praxis-maas-block-temp`: deleted
  07:44:44.
- Next calls (07:45:01, 07:45:12, 07:45:19): `step="maas"` status 200.
- `oc get adminnetworkpolicy` after the run: `No resources found`. The
  `trap` was not needed. No script or port-forward left.
