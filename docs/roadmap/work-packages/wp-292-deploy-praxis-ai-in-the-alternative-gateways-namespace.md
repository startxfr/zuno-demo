# WP-292: Deploy Praxis AI in the alternative gateways namespace

- **State:** Done (2026-11-18): live on demo333 with the local models, Claude, Codestral, the per-subject limit, OpenTelemetry, the fallback (proven live 2026-11-18), the SaaS tools rule (live 2026-11-18) and the Redis idle-timeout fix (proven live 2026-11-18 after 65 idle minutes)
- **ADRs:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Depends on:** [WP-291](wp-291-install-openshift-pipelines-and-build-praxis-ai-from-source.md)
- **Related:** [ADR-0620](../../adr/0620-build-third-party-images-from-source-with-openshift-pipelines-and-push-them-to-quay-io.md)
- **Target:** v0.17
- **Estimated files touched:** ~25: the praxis chart, its app pair and role, the namespace entry, six allow-lists, the checks

## Goal

Praxis serves `auto`, the four local models, Claude and Codestral in `zuno-ai-gateways`, behind the `zuno` JWT. The Zuno ai-gateway is unchanged.

## Steps

1. **Spike** (local podman, a stub OpenAI backend). Confirm the configuration of:
   - the `policy` filter verifying a Keycloak RS256 JWT (JWKS, issuer, audience `zuno-admin-api`);
   - the `auto` rewrite;
   - `anthropic_messages_to_chat_completions` and `openai_chat_completions_to_anthropic`;
   - `token_rate_limit` (`authenticated_subject`, redis backend);
   - NeMo guardrails;
   - OTel.

   Write `docs/roadmap/evidence/wp-292-praxis-spike.md`.
2. **Namespace** in `gitops/charts/namespaces/values.yaml`:
   - mesh labels;
   - PeerAuthentication STRICT and a port-8080 exception, copied from `ai-gateway-from-unmeshed-clients`;
   - EgressFirewall: Keycloak, `api.anthropic.com`, `api.mistral.ai`;
   - extend `platform/security/check_mesh_mtls.py`.
3. **Allow-lists** gain the namespace and the `praxis` pod or ServiceAccount:
   - `gitops/charts/models/templates/networkpolicy-*.yaml`;
   - MaaSSubscriptions in `gitops/charts/models/values.yaml`;
   - `gitops/charts/redis/templates/networkpolicy.yaml`;
   - `allowedFromNamespaces` of `zuno-auth` and `zuno-monitoring`;
   - `zuno-mesh`;
   - the Vault grants for anthropic, mistral-codestral and redis.
4. **Chart `gitops/charts/praxis`**:
   - Deployment, Service `praxis:8080`, ServiceAccount with the projected MaaS token;
   - the rendered `praxis.yaml` ConfigMap;
   - service-CA trust and `excludeOutboundPorts: "8000"`;
   - ExternalSecrets;
   - ingress NetworkPolicy: experience-client namespaces, `zuno-unifai` multiagent, the `zuno-agent-gateway` proxy;
   - ServiceMonitor and a Grafana dashboard;
   - hardening per `check_workload_hardening.py`.
5. **Wiring:**
   - app pair `gitops/apps/praxis/`;
   - role `ansible/roles/praxis` and the day2 playbooks;
   - `DAY2_RUN_COMPONENTS`;
   - AAP surveys;
   - `zuno_praxis_enabled` in `ansible/clusters/demo333.yml`.
6. **Live**, with the owner's go: the allow-lists, then Praxis.

## Acceptance

- `/v1/models` refuses a call without a token (401) and lists the models with a Keycloak token.
- `auto`, each local model, Claude and Codestral answer.
- `/v1/messages` answers through the translation.
- The per-subject limit returns 429.
- Tempo shows the Praxis spans, and Prometheus scrapes its metrics.
- The Zuno ai-gateway's day2 check and golden-path probes are unchanged.

## Result, part B: the chart and its wiring (2026-11-17, repo)

Repo work done; nothing is applied to the cluster. Part A (the namespace and the allow-lists) is the previous commit.

- **Chart `gitops/charts/praxis`:** ConfigMaps for `praxis.yaml`, the policy and the Claude routing overlay (three directories),
  a Deployment, the Service (8080 and the metrics port 9902), the ServiceAccount, the ExternalSecrets, the ingress
  NetworkPolicy and the ServiceMonitor. No image digest, no Deployment.
- **Behaviour,** proven against the real image in a local rig ([evidence](../evidence/wp-292-praxis-chart-2026-11-17.md)): the zuno
  JWT, the model list, `auto`, MaaS first then KServe, `/v1/messages`, streaming, and the refusal of the SaaS models for the
  `claude-code` client.
- **Switches:** `saas`, `tokenRateLimit` and `opentelemetry`, all off by default. The last two need our own build.
- **Wiring:** the Application pair `gitops/apps/praxis`, the role `ansible/roles/praxis`, the Makefile list, the day-2 playbooks, the
  AAP surveys and DAGs, `zuno_praxis_enabled` in `ansible/clusters/demo333.yml`; the models and redis roles read the same switch to
  admit the Praxis pod. The Vault grants (`zuno-ai-gateways`: the two provider keys and the session store) and the SecretStore are
  here, with the ExternalSecrets that read them.
- **Open points:** the TLS to the models and the MaaS certificate, the SaaS providers, the OTLP port (4317, not 4318),
  `token_rate_limit`, and the PeerAuthentication exception for the metrics port 9902 (part A has 8080 only). See the evidence.
- **Live steps remaining,** each with the owner's go: the allow-lists (`make d2 install models`, `make d1 install redis`), the
  image digest from `make d2 build praxis`, then `make d2 install praxis`.


## Live, 2026-11-17

The owner gave the go for the deploy. The image is the WP-291 fork build, pinned at `sha256:3daccf8e…` in `50c0b508`. The runs were `make d2 install models`, `make d1 install redis` and `make d2 install praxis`, from a worktree on devel `50c0b508`, with `confidential.yml` passed as extra vars.

- **Applications:** `zuno-praxis-d0` and `-d1`, `zuno-models-d0` and `-d1`, and `zuno-redis-d0` are Synced and Healthy.
  - `zuno-redis-d1` first showed sync status Unknown: the repo-server comparison timed out (`DeadlineExceeded`), so the role's wait read the old Synced status. A refresh and the next sync at `50c0b508` brought the session-store NetworkPolicy, which now admits the Praxis pod.
- **No roll of the models:** the vLLM and router pods kept their 4-day age. The ai-gateway pods kept their 2-day age. `make d2 check models` passes.
- **Praxis pod:** `praxis` is 2/2 Running in `zuno-ai-gateways`.
- **Calls,** through `oc port-forward` with a `zuno-evaluations` token of the persona `consultant-01`:

  | Call | Result |
  |---|---|
  | `GET /v1/models`, no token | 401 |
  | `GET /v1/models`, token | 200: `auto`, `qwen3.6-27b-instruct`, `gpt-oss-20b`, `qwen3.5-9b`, `qwen3.5-9b-wesh` |
  | chat `auto` | 200, served by `qwen3.6-27b-instruct` (9.5 s, cold prompt) |
  | chat `gpt-oss-20b` | 200 (0.3 s) |
  | chat `claude-sonnet-4-5` | 403 `model_not_allowed` |
  | `POST /v1/messages`, `auto` | 200, an Anthropic `message` from `qwen3.6-27b-instruct` |
  | `POST /v1/messages`, streamed | 200, events `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop` |

- **Path:** every accepted call was served by the `maas` step of the router (Praxis log `step="maas"`), with the projected ServiceAccount token. The four `<model>-praxis` MaaSSubscriptions have the Praxis ServiceAccount as their only owner.
- **Metrics:** Prometheus scrapes the `praxis` job on port `metrics` (`up` = 1, 26 series, among them `praxis_ai_intelligent_route_*` and `praxis_http_request_duration_seconds`).
- **Not yet proven live:**
  - Claude and Codestral (`zuno_praxis_saas_enabled`);
  - the per-subject limit and its 429 (`zuno_praxis_token_rate_limit_enabled`);
  - the Tempo spans (`zuno_praxis_otel_enabled`);
  - the fallback from MaaS to the direct KServe path, which needs MaaS to fail;
  - the workstation entry (WP-298).

### The three switches, 2026-11-17 evening

The owner gave the go to turn on SaaS, the per-subject limit and OpenTelemetry (`demo333.yml`). Each problem found was fixed in the chart or the build, pushed, and installed again.

| Finding | Fix | Commit |
|---|---|---|
| `praxis-ai --validate` refused `redis://:${REDIS_PASSWORD}@…`: "backend.url supports one complete ${ENV_VAR} reference" | The `praxis-redis` ExternalSecret templates `REDIS_URL`, with the password percent-encoded | `0800ec74` |
| Codestral 502 "TLSHandshakeFailure … reset by peer, SNI api.mistral.ai". RHOAI's rule `zuno-ai-run/mistral-large` (tls SIMPLE, exported to every namespace) made the sidecar add a second TLS layer | A DestinationRule per SaaS host in `zuno-ai-gateways`, selecting the praxis pod, tls DISABLE (as WP-124 did for the ai-gateway) | `6a6ac7ce` |
| Claude 404: `claude-3-5-sonnet-latest` is retired | `claude` targets `claude-opus-5-5` | `6a6ac7ce` |
| No OTLP export: "the `otel` feature is not enabled". The server's `opentelemetry` feature is empty | Both build sources add `praxis-core/otel,praxis-filter/otel,praxis-protocol/otel`; rebuilt as `praxis-build-nz69t` (25 min), pinned `sha256:e319e228…` | `6a6ac7ce`, `eb163524` |
| After the 429 proof at capacity 2000, the install at 1000000 answered 503 to everyone, personas never counted included: "admission backend failed, failing closed error=configuration_mismatch" | The Redis namespace is `praxis-<8 hex of window/capacity/reservation>`, so a new rule starts on new keys | `65d6b63f` |

- **Proofs:** with persona tokens, through a port-forward, on the final image.
  - `/v1/models` lists the five local models, `claude` and `codestral-latest`.
  - `auto`, `gpt-oss-20b`, `claude` and `codestral-latest` answer `pong`. `/v1/messages` answers, plain and streamed.
  - An unlisted model gets 403.
  - With `-e zuno_praxis_token_rate_limit_capacity=2000`, the second call of `ai-dev-01` got 429 with `x-ratelimit-limit-tokens: 2000`, `x-ratelimit-remaining-tokens: 0` and `retry-after: 3613`. The install was then run again at the default 1000000.
  - Tempo (`zuno-monitoring/tempo-tempo`) holds traces of service `praxis`: 4 for 41 calls at the 0.1 sampling rate.
- **Role finding:** twice, the role's wait passed before Argo CD had synced the new revision, because it read the Application's previous status. The checks above were made after the sync.
- **Outside this WP:** the Zuno ai-gateway's `platform/ai-gateway/provider-routing.yaml` still names `claude-3-5-sonnet-latest` for its Anthropic fallback. It was left unchanged (ADR-0619: the default gateway is not touched); it is reported to the owner.

## 2026-11-18: the fallback, the workstation entry and tools on SaaS models

- **Fallback.** The proof of 2026-11-17 failed twice ([evidence](../evidence/wp-292-fallback-live-2026-11-17.md)). Both
  defects were reproduced on a local bench and fixed in `318e65e2`.
  - Praxis's router drops `Content-Type` on the second step's sub-request, and vLLM answered 400. The direct step now
    sets `content-type: application/json`.
  - A silently dropped MaaS connection waited the 600 s deadline. The MaaS cluster now has a 5 s connect and a 180 s
    read timeout. `step_timeout_ms` is not used, because it also cuts the direct step and a streamed answer.

  The re-run on demo333 ([evidence](../evidence/wp-292-fallback-live-2026-11-18.md), `26b7b2ec`) answered every blocked
  call through the direct step, in 14 s at most.
- **First call after an idle hour.** The re-run's baseline call got 503 with an empty body in 1.1 s. Praxis logged
  `token_rate_limit` "reserve" on `shared_kv` failing with "unavailable", then "admission backend failed, failing
  closed". It was the only such failure in 12 h of logs, on the first call after about eight idle hours, and the next
  calls passed.
  - **Cause.** Envoy's default TCP idle timeout, 1 h, on both sidecars. The praxis sidecar's TCP proxy to
    `zuno-redis-master` had no `idle_timeout`, and neither had the Redis sidecar's inbound one. Redis itself never
    closes an idle client (`timeout 0`). Praxis's token limit keeps one multiplexed Redis connection (fork source,
    `filters/src/token_rate_limit/valkey/connection.rs`). It finds the connection closed only on the next call: that
    reservation fails, the filter fails closed, then drops the connection, and the call after reconnects. So every pause
    of more than an hour cost the next call, not only a night.
  - **Confirmed live, 2026-11-18.** No Praxis-to-Redis bytes from 08:13:20Z to 09:15:31Z (sidecar counters unchanged).
    The first call at 09:15:39Z got 503, empty body, 1.1 s, with the same two log lines. The second call got 200.
  - **Fix.** The idle timeout is off on both sides, and the fail-closed rule is kept.
    - `praxis-redis-idle`, a DestinationRule of the praxis chart, applies to the praxis pod only: `tcp.idleTimeout: 0s`,
      no tls, so the mesh's automatic mutual TLS is unchanged.
    - `zuno-redis-inbound-idle`, an EnvoyFilter of the redis chart in `zuno-auth`, applies to the Redis pods and port
      6379 only: it merges `idle_timeout: 0s` into the inbound TCP proxy. A Sidecar with
      `inboundConnectionPool.tcp.idleTimeout: 0s` was tried first (`12669efb`). Istio 1.30 put that value on the
      inbound cluster's HTTP idle timeout and left the TCP proxy at 1 h, seen in the Redis sidecar's `config_dump`. The
      supported knob, the proxy metadata `IDLE_TIMEOUT`, needs a pod annotation and so a Redis restart. The owner chose
      the EnvoyFilter, which needs no restart. It must be checked after every Istio upgrade, because Istio ignores an
      EnvoyFilter whose match no longer applies.

    Both were validated by a server-side dry run before the push. The other options were `backend.on_failure: open`,
    which would turn the limit off silently during a real Redis outage, and a retry in Praxis itself (upstream, after
    the demo).
  - **Proven live, 2026-11-18.** Both sidecars' `config_dump` show `idle_timeout: 0s`: the praxis sidecar's outbound
    TCP proxy to `zuno-redis-master` and the Redis sidecar's `inbound|6379||` TCP proxy. The praxis pod's sidecar counters
    to Redis then stayed unchanged from 10:28:04Z at the latest (they were read every 5 minutes) to 11:33:26Z, more than
    the 62 minutes of the morning failure. The two calls at 11:33:26Z, persona `consultant-01`, model `gpt-oss-20b`, got
    200 in 0.5 s and 0.3 s, and Praxis logged no token-limit failure.

    One more 503 came from Open WebUI at 09:51:53Z, 27 idle minutes after the EnvoyFilter was applied. Its most likely
    cause is the change itself, not proven: the warm-up call at 09:24:52Z reused the connection opened before the
    change, and the Redis sidecar closed it when it drained its old inbound listener. No 503 followed.
- **Workstation entry.** `praxis.<domain>` on `zuno-agent-gateway` is live (`e4d18370`, WP-298 step 0).
- **Tools on SaaS models** ([ADR-0619 update of 2026-11-18](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)).
  The SaaS route ends with an OPA step, `files/saas-no-tools.rego`. Proven on the pinned image
  (`sha256:e319e228…`) with the rendered policy, on a local bench with a stub backend:

  | Call | Result |
  |---|---|
  | local model, with or without tools | 200 |
  | `claude`: no tools, `tools: []`, `tools: null` | 200 |
  | `claude`: tools; legacy `functions`; a `tool` message in the history | 403 `saas_tools_not_allowed` |
  | `codestral-latest` with tools | 403 `saas_tools_not_allowed` |
  | `/v1/messages` `claude`: no tools; text blocks only | 200 |
  | `/v1/messages` `claude`: tools; `tool_use` and `tool_result` blocks in the history | 403 `saas_tools_not_allowed` |
  | streamed `claude` call with tools | 403 `saas_tools_not_allowed` |
  | an unlisted model | 403 `model_not_allowed` |

  **Live on demo333, 2026-11-18** (owner's go; pushed as `3d5320f0`, Argo CD synced it and the pod rolled at
  08:11:30Z). Through a port-forward, persona `consultant-01`:

  | Call | Result |
  |---|---|
  | `claude`, no tools | 200 `pong`, 1.2 s |
  | `claude` with a Zuno-style tool (`confluence.page.search`); `claude` with a tool result in the history | 403 `saas_tools_not_allowed` |
  | `codestral-latest` with a tool; `/v1/messages` `claude` with a tool | 403 `saas_tools_not_allowed` |
  | `gpt-oss-20b` with a tool; with a tool result in the history | 200 `pong` |
