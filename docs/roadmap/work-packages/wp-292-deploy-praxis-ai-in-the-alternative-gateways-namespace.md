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
