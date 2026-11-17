# WP-292: Deploy Praxis AI in the alternative gateways namespace

- **State:** Operator pending (2026-11-17): live on demo333 with the local models; left: the SaaS models, the per-subject limit, OpenTelemetry and a live fallback proof, each behind its own switch and the owner's go
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
