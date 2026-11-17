# WP-292: Deploy Praxis AI in the alternative gateways namespace

- **State:** Not started
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

