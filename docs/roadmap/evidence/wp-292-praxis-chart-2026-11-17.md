# WP-292 part B: the Praxis chart, validated against the real image, 2026-11-17

Repo-only check of `gitops/charts/praxis` ([WP-292](../work-packages/wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md),
[ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)). Nothing ran on a
cluster. The spike of the same day ([wp-292-praxis-spike.md](wp-292-praxis-spike.md)) proved the filter structure; this
checks the chart that renders it.

## Method

- Image: `ghcr.io/praxis-proxy/ai:latest`, upstream 0.11.0, `podman`, no network to a cluster.
- **Configuration test:** the chart is rendered with `helm template`; `praxis.yaml` and `policy.yaml` are mounted read-only in
  directories of their own, and the image runs `-t -c <praxis.yaml>`. A dummy token file and a throwaway CA stand for the
  projected ServiceAccount token and the service CA, because the image reads both at start.
- **Functional rig:** the rendered configuration with every cluster pointed at local stubs (no TLS), the JWKS served by a stub, and
  tokens signed with a throwaway RS256 key (issuer `https://keycloak.apps.mycluster.example.com/realms/zuno`, audience
  `zuno-admin-api`, `azp` set per call). N=1 for each call below. The stubs and the key are throwaway and are not in the
  repository.
- Offline test: `platform/praxis/tests/test_praxis_chart.py` (10 tests, `helm template`, no image).

## Results

`-t` accepted the rendered configuration with the default values and with `saas.enabled=true`. With `tokenRateLimit.enabled=true`
it answered `unknown filter type: 'token_rate_limit'`: the published image does not have the filter (our build does, ADR-0620), so
those two switches are **not** proven here. OpenTelemetry gave no error, but the published image only warns when its `otel` feature is
absent.

| Call | Answer |
|---|---|
| `GET /v1/models` without a token | 401 `auth.missing_credential` |
| the same with a malformed token | 401 `auth.malformed_credential` |
| the same with a valid token | 200, the five sovereign models (and the two SaaS names when on) |
| `auto`, MaaS stub answering 503 | 200 from the direct stub, model `qwen3.6-27b-instruct` |
| each of the four models, MaaS stub answering 200 | 200; the stub saw `/zuno-ai-run/<service>/v1/chat/completions` with a bearer from the token file |
| `POST /v1/messages` for `qwen3.5-9b` | 200 as an Anthropic message, through the MaaS step |
| `stream: true` on `auto` | 200, SSE |
| a model that is not listed (`gpt-4o`) | 403 `model_not_allowed` |
| azp `claude-code`, `claude` or `codestral-latest`, on `/v1/chat/completions` and on `/v1/messages` | 403 `model_not_allowed_for_client` |
| azp `claude-code`, a local model | 200 |
| another azp, `codestral-latest` | 200 from the stub (the Codestral step runs only for that model) |
| another azp, `claude` | the request reaches the Anthropic translator; the stub is not Anthropic, so 502 |
| `/ready`, `/healthy`, `/metrics` on the metrics port | 200 |

The routing overlay of the Claude candidate is checked by the image: a changed digest is refused with `envelope digest mismatch`,
and the digest the chart computes (SHA-256 of the sorted-key JSON of `{candidates, local_site, network}`) is accepted.

## Findings

1. **A router must end its chain.** Three routers (local, Claude, Codestral) in one chain are refused: `must be the last filter in
   chain`. The chart makes one chain per router, and a condition on X-Model skips the routers that are not for the model.
2. **Several `path_rewrite` in one step** need `allow_rewrite_override: true` on the later ones; only the one whose X-Model condition
   holds runs.
3. **`claim.azp`, not `client.client_id`.** With the keycloak preset, `client.client_id` is filled only for a client-role resolver;
   the rule `client.client_id == 'claude-code'` never matched. `claim.azp == 'claude-code'` does, with the one user resolver.
4. **A static candidate cannot carry the Anthropic provider profile.** `api_format`, `path` and `target_model` are overlay fields, so
   the Claude candidate comes from a content-addressed overlay in its own ConfigMap. The translator also needs
   `api_translation_enabled: true`, or it answers 503 `api_translation_disabled`.
5. **The admin API must be on loopback.** `/metrics`, `/ready` and `/healthy` are served on `admin.metrics_address`, which may be
   public: the chart uses `127.0.0.1:9901` for the admin API and `0.0.0.0:9902` for the metrics, the Service and the probes. `/` on 8080
   goes through the policy and answers 401, so it is no probe.
6. **The JWKS is read through the public Route**, which resolves to the router's private address in the cluster: the policy filter
   lists the issuer's host in `trusted_private_endpoints` (narrower than `allow_private_idp`).
7. **The IRR deadline is 30 s by default**, and it also cuts a streamed answer: the chart sets `timeout_ms: 600000`.
8. **Number formatting:** a Helm number such as 4194304 is rendered as a float and refused where Praxis wants an integer; the chart
   casts with `int64`.

## Not proven here

- TLS to the models (the service CA, the SNI and the `Host` of the MaaS gateway and of KServe): the rig ran without TLS.
- The MaaS call with a real projected token, and whether the MaaS gateway's certificate is signed by the service CA.
- Claude and Codestral against the real providers, and the Anthropic translation of an Anthropic answer.
- `token_rate_limit` on Redis, the order of `token_rate_limit` and `token_count`, and the OTLP transport (the chart uses the gRPC
  port 4317; the collector also serves 4318).
- The ServiceMonitor scrape: the PeerAuthentication exception of `zuno-ai-gateways` covers port 8080 only, and the metrics port 9902
  is plaintext for Prometheus.
