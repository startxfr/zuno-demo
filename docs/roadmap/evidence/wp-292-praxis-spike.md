# WP-292 Praxis AI spike, 2026-11-17

Local spike for [WP-292](../work-packages/wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md), step 1
([ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)). It checks
what the configuration of Praxis AI can do before the chart is written.

**Run by `zuno-demo`, files read by the writer.** The commands, the times and the results come from the session that ran
the spike (as relayed). The writer read the configuration files and the three stub logs directly and quotes them below.
The writer did not run the spike.

## Setup

- Date and place: 2026-11-17, 13:05 to 13:38 CET (as relayed), on the presenter's workstation, with `podman` and
  `--network host`. No cluster, no cluster action.
- Image: `ghcr.io/praxis-proxy/ai:latest`, which is upstream `praxis-proxy/ai` 0.11.0, revision
  `0c6fd76f597f90d49cbee005ec9461ce8896b0f5`, digest
  `sha256:c36a81406ddc7bc1b9ce37731181272e75c94e7f1fb4598a6bac10330f2581ac`. The fork's own image
  (`quay.io/modden/praxis-ai`) is private: the pull was refused as unauthorized. So the spike ran upstream 0.11.0, not
  the fork that ADR-0619 names as the default source.
- Stubs, one Python file (`stub.py`) on three ports:
  - 3100 serves the JWKS of a throwaway RS256 test key;
  - 3999 always answers 503 and stands for the MaaS gateway;
  - 3002 is an OpenAI chat stub and stands for direct KServe.
- Tokens: minted with PyJWT, issuer `https://keycloak.example/realms/zuno`, audience `zuno-admin-api`, key id `spike`.
  The test key and its JWKS are throwaway and are not copied into the repository.
- Every result below is one run (N=1), unless a count is given.

## Configuration tested

`praxis.yaml` (the gateway), as read from the spike directory:

```yaml
listeners:
  - name: gateway
    address: "0.0.0.0:8080"
    filter_chains: [main]
filter_chains:
  - name: main
    filters:
      - filter: policy
        config_path: /spike/policy.yaml
        allow_private_idp: true
        require_protocol_metadata: false
        llm:
          require_model: true
          provider: openai
      - filter: anthropic_messages_request
        on_invalid: continue
      - filter: anthropic_messages_to_chat_completions
        allow_lossy_features: [prompt_caching, extended_thinking]
        conditions:
          - when:
              path: "/v1/messages"
      - filter: anthropic_messages_to_chat_completions_stream
        response_conditions:
          - when:
              headers:
                content-type: "text/event-stream"
      - filter: model_to_header
        header: X-Model
      - filter: iterative_request_router
        initial_step: maas
        steps:
          - name: maas
            filters:
              - filter: headers
                request_remove: [authorization, x-api-key]
              - filter: path_rewrite
                replace:
                  pattern: "^/v1/(chat/completions|messages)$"
                  replacement: "/zuno-ai-run/qwen36-27b-instruct/v1/chat/completions"
                conditions:
                  - when:
                      headers:
                        x-model: "auto"
              - filter: model_to_provider
                models:
                  - {model: auto, upstream: maas, target_model: qwen3.6-27b-instruct, paths: [/v1/chat/completions, /v1/messages, /zuno-ai-run/qwen36-27b-instruct/v1/chat/completions, /zuno-ai-run/qwen36-27b-instruct/v1/messages]}
              - filter: load_balancer
                clusters:
                  - name: maas
                    endpoints: ["127.0.0.1:3999"]
            on_result:
              - status: [429, 502, 503, 504]
                next: direct
              - default: true
                done: true
          - name: direct
            filters:
              - filter: headers
                request_remove: [authorization, x-api-key]
              - filter: path_rewrite
                replace:
                  pattern: "^/v1/messages$"
                  replacement: "/v1/chat/completions"
                conditions:
                  - when:
                      path: "/v1/messages"
              - filter: model_to_provider
                models:
                  - {model: auto, upstream: direct-qwen36, target_model: qwen3.6-27b-instruct, paths: [/v1/chat/completions, /v1/messages]}
              - filter: load_balancer
                clusters:
                  - name: direct-qwen36
                    endpoints: ["127.0.0.1:3002"]
            on_result:
              - default: true
                done: true
insecure_options:
  allow_private_endpoints: true
```

`policy.yaml` (identity and authorization):

```yaml
plugins:
  - name: keycloak
    kind: identity/jwt
    hooks: [identity.resolve]
    on_error: fail
    capabilities: [perform_http]
    config:
      header: Authorization
      trusted_issuers:
        - issuer: "https://keycloak.example/realms/zuno"
          audiences: ["zuno-admin-api"]
          algorithms: ["RS256"]
          decoding_key:
            kind: jwks_url
            url: "http://127.0.0.1:3100/jwks.json"
            insecure_http: true
          leeway_seconds: 60
      claim_mapper: keycloak
global:
  authentication:
    - keycloak
  authorization:
    pre_invocation:
      - "require(authenticated)"
routes:
  - http:
      path_prefix: /v1/models
    authorization:
      pre_invocation:
        - "require(authenticated)"
  - llm: [auto, qwen3.6-27b-instruct, gpt-oss-20b, qwen3.5-9b, qwen3.5-9b-wesh, claude, codestral-latest]
    authorization:
      pre_invocation:
        - "require(authenticated)"
  - llm: "*"
    authorization:
      pre_invocation:
        - "deny('model is not permitted', 'model_not_allowed')"
```

`insecure_http: true`, `allow_private_idp`, `allow_private_endpoints` and the three stub endpoints are spike-only
settings. The model names `claude` and `codestral-latest` are in the allow-list but were never called (see "Not
tested").

## Results

1. **Configuration validation** (`praxis-ai -t -c praxis.yaml`) passes after three fixes. Each is a finding:
   - The JWT plugin refuses an `http` JWKS address (`JWKS URL must use https://`). `insecure_http: true` was used for the
     spike only. In the cluster the gateway must read the JWKS from the `https` Keycloak route, not from the in-cluster
     `http` Service. **This differs from ADR-0619 clause 4**, which names the in-cluster `zuno-service.zuno-auth.svc`.
   - The plugin needs `capabilities: [perform_http]` to fetch the JWKS.
   - `anthropic_messages_to_chat_completions` accepts only the lossy features `extended_thinking` and `prompt_caching`.
     The upstream example's `mid_conversation_system` is refused.
   - The `policy` filter needs `allow_private_idp: true` for a private JWKS host, and `require_protocol_metadata: false`
     for an identity-only use (no MCP routes).
2. **Identity and model allow-list.** No token: 401. A valid token and the model `auto`: 200, and the body's model is
   rewritten to `qwen3.6-27b-instruct` by `model_to_provider`. An unknown model (`gpt-5`): 403 with
   `{"code":"model_not_allowed"}`, from the `llm: "*"` deny route.
3. **MaaS, then direct.** `iterative_request_router`: the step `maas` got 503 from port 3999, the step `direct` got 200
   from port 3002. The log line is `sub-request complete step=direct iteration=1 status=200`. The `maas` step rewrites the
   path to `/zuno-ai-run/qwen36-27b-instruct/v1/chat/completions`, and the log of stub 3999 shows it.
4. **Anthropic Messages.** `POST /v1/messages` with the model `auto` is translated to chat completions, answered by the
   stub, and translated back to an Anthropic message (`type: message`, `stop_reason: end_turn`, `usage` present). With
   `stream: true` the answer is Anthropic server-sent events: `message_start`, `content_block_start`, then
   `content_block_delta` three times.
5. **Findings fixed during the spike.**
   - A `path_rewrite` placed before `iterative_request_router` is not seen by the router's sub-requests: the upstream got
     `/v1/messages`. The rewrite must sit inside each step.
   - Two `path_rewrite` filters in one step do not compose: the last one wins. Use one regex rewrite per case, for
     example `^/v1/(chat/completions|messages)$`.
   - The client's `Authorization` header reached the MaaS stub until a `headers` filter with
     `request_remove: [authorization, x-api-key]` was added at the start of each step. After that, no client token reaches
     any backend (the stub logs show `auth=no`).
6. **`token_rate_limit` is not in the published images.** The filter answered "unknown filter type" in all three
   published images (`latest`, `latest-experimental`, `nightly`). It needs our own build with the
   `token-rate-limit-filter` feature (ADR-0620, WP-291). The configuration tried is `trl.yaml`:

   ```yaml
   listeners:
     - {name: g, address: "0.0.0.0:8081", filter_chains: [main]}
   filter_chains:
     - name: main
       filters:
         - filter: token_rate_limit
           rules:
             - name: per-user
               window: 1h
               capacity: 100000
           key: authenticated_subject
         - filter: router
           routes: [{path_prefix: "/", cluster: c}]
         - filter: load_balancer
           clusters: [{name: c, endpoints: ["127.0.0.1:3002"]}]
   insecure_options:
     allow_private_endpoints: true
   ```

## What the stub logs show

Read by the writer. The logs hold the method, the path and `auth=yes` or `auth=no` for each request. They hold no token.

| Log | Lines | Content |
|---|---|---|
| `stub3002.log` (direct KServe stub) | 4 | `POST /v1/chat/completions` three times and `POST /v1/messages` once, all `auth=no`. The `/v1/messages` line is the finding of the rewrite placed before the router. |
| `stub3999.log` (MaaS stub) | 5 | Three `POST /zuno-ai-run/qwen36-27b-instruct/v1/chat/completions` and two `.../v1/messages`. The first three have `auth=yes`, the last two `auth=no`. |
| `stub3100.log` (JWKS stub) | 365 | 365 `GET /jwks.json`. |

- The `auth=yes` lines of the MaaS stub are consistent with the finding that the client's header reached it before the
  `headers` filter was added. The order of the lines and the run each belongs to were not checked against the spike's
  shell history.
- **Observation, cause not determined:** 365 JWKS fetches is far more than the number of requests listed above. The
  spike's session did not say how many requests it sent in total. Whether the plugin refetches the JWKS on every request,
  on a timer, or on retries was not measured. WP-292 should measure it before the gateway sits in front of the real
  Keycloak.

## Not tested

- Claude through `openai_chat_completions_to_anthropic`, and Codestral.
- NeMo guardrails.
- The OpenTelemetry export (the image has the feature only in an own build, ADR-0620).
- The MaaS credential. A static `credential_injection` cannot follow the hourly projected ServiceAccount token.
  `credential_inject` with `file` has a watcher but is driven by `intelligent_route` or `provider_route`. This is to be
  settled in WP-292. The spike's `headers` filter only proves that the client's token is not forwarded; it adds no
  credential for MaaS.
- Real Keycloak tokens, and the `https` JWKS route.
- The fork's image and its differences from upstream (the pull was refused).

## What WP-292 takes from it

- The JWKS address must be `https`: use the Keycloak route, and check the service-CA or public trust of the pod.
- Give the JWT plugin `capabilities: [perform_http]`; keep the `policy` filter with `require_protocol_metadata: false`.
- Put the path rewrite and the removal of the client's authorization inside each router step.
- Use one regex rewrite per step.
- Restrict the lossy features of the Anthropic translation to the two it accepts.
- Build with `token-rate-limit-filter` and `opentelemetry` (already in ADR-0620's list) before testing the per-subject
  limit and the traces.
- Settle the MaaS credential and measure the JWKS fetch rate before the live step.
- ADR-0619 clause 4 names the in-cluster JWKS address, which the plugin refuses. The owner of that ADR decides how to
  amend it; this file does not change it.
