# ADR-0619: Run Praxis AI as an alternative AI gateway next to the default Zuno ai-gateway

- **Status:** Accepted
- **Target:** v0.17
- **Date:** 2026-11-17
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md),
  [ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md),
  [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md),
  [ADR-0565](0565-derive-data-classification-from-okf-and-only-allow-raising-it.md),
  [ADR-0606](0606-admit-new-experiences-with-a-definition-of-done-and-a-wip-limit.md),
  [ADR-0610](0610-generate-blender-objects-as-bpy-scripts-from-a-local-model-through-the-ai-gateway.md),
  [ADR-0620](0620-build-third-party-images-from-source-with-openshift-pipelines-and-push-them-to-quay-io.md)

## Context

The owner wants the demo to show other AI gateways next to the Zuno ai-gateway (2026-11-17). The aim is to show that the
same clients can be served through them in alternative scenarios. The Zuno ai-gateway stays the default for every demo
and is not changed. Praxis AI comes first, then LiteLLM ([ADR-0621](0621-run-litellm-as-an-alternative-ai-gateway.md)),
Agent Router ([ADR-0622](0622-run-agent-router-as-an-alternative-ai-gateway.md)) and Bifrost
([ADR-0623](0623-run-bifrost-as-an-alternative-ai-gateway.md)). This record holds the frame the four share.

A feature comparison made on 2026-11-17 covered the four gateways against the Zuno ai-gateway and mcp-gateway. None of
the four carries:
- the signed delegation chain or the per-call assertions;
- signed agent bundles (OKF);
- classification floors that only rise (ADR-0565);
- per-(agent, task) policy.

Those stay in the Zuno gateways. Replacing the mcp-gateway is out of scope; ADR-0571's reason, no agent and task rights,
holds for these products too.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Praxis AI is an alpha Rust AI gateway on the Praxis proxy. `redhat-et/praxis-ai` is Red Hat Emerging Technologies' fork of `praxis-proxy/ai` for the EnMaaS images. Version 0.10.0, no release, no Helm chart or operator. | `README.md`, `DOWNSTREAM.md`, `Cargo.toml` of `redhat-et/praxis-ai` at `0c024ef` (2026-11-11) |
| F2 | Praxis translates Anthropic Messages to Chat Completions and back, streaming included. It adapts Chat Completions to Anthropic, Azure, Bedrock and Vertex. It can call NeMo Guardrails, emits `routing.select` / `provider.route` spans, and has vLLM-aligned TTFT/TPOT metrics. | `docs/features.md`, `docs/architecture/opentelemetry.md`, `docs/llm-metrics.md`, `filters/src/guardrails/providers/nemo.rs` |
| F3 | Some needed capabilities sit behind Cargo features: token rate limiting (`token-rate-limit-filter`, experimental) and OpenTelemetry (`opentelemetry`). JWT verification is in the `policy` filter (`policy-engine`, part of `full`). Using these needs our own build. | `server/Cargo.toml` `[features]`, `docs/filters/token_rate_limit.md`, `docs/architecture/cryptographic-inventory.md` |
| F4 | Every demo client sends a `zuno` Keycloak JWT to the ai-gateway: the user's own token (Open WebUI, UnifAI, Blender, world-model) or a client-credentials token through zuno-token-proxy or the OpenClaw operator. | `gitops/charts/open-webui/values.yaml` (`system_oauth`), `gitops/charts/unifai/values.yaml` (`gatewayLLM`), `components/zuno-token-proxy/app/main.py` |
| F5 | Each client's egress NetworkPolicy admits only `zuno-ai-run:8080`, and each takes a single gateway URL in its values. | `gitops/charts/open-webui/templates/networkpolicy-egress.yaml`, `gitops/charts/zuno-token-proxy/templates/networkpolicy.yaml`, `gitops/charts/world-model/templates/networkpolicy.yaml` |
| F6 | The backends admit only the `ai-gateway` identity of `zuno-ai-run`: local-model NetworkPolicies, the Redis NetworkPolicy, the MaaSSubscriptions keyed on its ServiceAccount, and the namespace's Vault key grants. | `gitops/charts/models/templates/networkpolicy-*.yaml`, `gitops/charts/redis/templates/networkpolicy.yaml`, `gitops/charts/models/values.yaml`, `platform/vault/secret-access.yaml` |

## Decision

**Praxis AI runs as an alternative AI gateway in a shared namespace `zuno-ai-gateways`, next to the Zuno ai-gateway,
which stays every client's default. The clients reach it through a second connection described by one generic list,
under the same Keycloak identity.**

1. **Zuno stays the default.** The Zuno ai-gateway, its routing, quotas, floors and guardrails are not changed. Every
   client keeps it as its first and default connection. An alternative gateway appears only as an additional,
   named connection, used by the alternative scenarios.
2. **One shared namespace for the alternatives.** Praxis and the later alternatives (ADR-0621 to ADR-0623) run in
   `zuno-ai-gateways`:
   - in the mesh, with STRICT mTLS and a port-8080 exception for the unmeshed clients (as `zuno-ai-run` has);
   - with a default-deny ingress baseline;
   - with an EgressFirewall that allows Keycloak and the two SaaS hosts only.

   Each backend allow-list of F6 gains this namespace and, where the list names a workload, the gateway's own pod or
   ServiceAccount.
3. **Sovereign models first; Claude and Codestral are the only SaaS models.**
   - Local models: `qwen3.6-27b-instruct`, `gpt-oss-20b`, `qwen3.5-9b` and `qwen3.5-9b-wesh`. Each goes through the
     RHOAI MaaS gateway first, then direct KServe, as in `platform/ai-gateway/provider-routing.yaml`.
   - SaaS: Anthropic Claude and Mistral Codestral, with the existing Vault keys `zuno/providers/anthropic` and
     `zuno/providers/mistral-codestral`, granted to the new namespace.
   - No other SaaS provider.
   - An alternative gateway exposes `auto`, mapped to `qwen3.6-27b-instruct`, so clients that send `auto` keep working.
4. **Same identity.** An alternative gateway must verify the `zuno` Keycloak JWT:
   - issuer `https://keycloak.<domain>/realms/zuno`;
   - JWKS read from the in-cluster `zuno-service.zuno-auth.svc`;
   - audience `zuno-admin-api`.

   A gateway that cannot verify it is fronted by zuno-token-proxy, which holds a client credential. The gateway then
   sees the proxy's identity, not the user's, and this limit is written in its scenario.
5. **The `altGateways` client contract.** Each client chart gets one values list:

   ```yaml
   altGateways:
     - {name: praxis, label: Praxis, url: http://praxis.zuno-ai-gateways.svc:8080/v1, models: [auto]}
   ```

   - It is empty by default.
   - From it the chart renders the extra connection and an egress rule to `zuno-ai-gateways:8080`.
   - A client is wired once, in its own work package. A later gateway is a new list entry, not a client change.
   - Clients that cannot hold two connections get the smallest change that does: a second ModelConfig, a second
     UnifaiLLM, an alternate token-proxy route, or a selector.
6. **This amends ADR-0587 clause 1.** That clause says an experience sends every model call to the ai-gateway. In the
   alternative scenarios it may also send a model call to an alternative gateway of `zuno-ai-gateways`. That gateway
   verifies the same JWT and holds the provider keys, so the client still holds none. Tools stay behind the mcp-gateway.
7. **Praxis is built by us and pinned by digest.**
   - Built from source with the features of F3 by the pipeline of
     [ADR-0620](0620-build-third-party-images-from-source-with-openshift-pipelines-and-push-them-to-quay-io.md),
     from the fork by default, with a switch to upstream.
   - Pushed to `quay.io/zuno/praxis-ai` and deployed by digest from the chart `gitops/charts/praxis`.
   - Its configuration is a rendered ConfigMap. Its traces go to the platform OTel collector, and its metrics are
     scraped by a ServiceMonitor.
8. **Claude Code is the band's second experience** (ADR-0606 clause 2; Blender of ADR-0610 is the first).
   - It reaches Praxis from the presenter's workstation on its own host on `zuno-agent-gateway`, with a public
     device-grant Keycloak client `claude-code`, as Blender does.
   - Praxis translates its Anthropic Messages calls for the sovereign models.
   - Its experience-client declaration goes into the agents release, like the others (ADR-0592).
9. **Three scenarios show it:**
   - `multi-gateway`: two clients in 5 minutes, every client in 15;
   - `claude-code-sovereign`;
   - `agents-alt-gateway`.

## Alternatives considered

- **Replace the Zuno ai-gateway or the mcp-gateway with Praxis.** Rejected. The four functions the owner holds
  non-negotiable (persona quotas, model roles and routing, identity and call security, traceability and OKF) are
  missing or partial (F1 to F3, and the 2026-11-17 comparison).
- **Put the alternative gateways behind the Zuno ai-gateway, as providers.** It keeps every Zuno function. It was not
  chosen because the clients would not visibly switch gateway, which is the point of the scenarios. It stays possible
  later: an alternative can also be added to `provider-routing.yaml`.
- **Run the alternatives in `zuno-ai-run`.** Fewer allow-lists to change, but they would mix with the governed path.
  The owner chose one shared namespace.
- **One namespace per alternative.** Cleaner removal, but four sets of allow-lists. Not chosen.

## Consequences

- The demo can show the same client on two or more gateways, with the differences visible: what each one enforces,
  and its traces and metrics.
- Model calls made through an alternative gateway lose these Zuno functions:
  - the persona quota ledger;
  - classification floors and signed tool-result markers;
  - per-agent routing policy;
  - the Zuno cost metrics.

  Limiting the alternatives to sovereign models plus two SaaS models bounds what can leave the cluster. The C3 data
  rule is kept by sending only C1 content in the alternative scenarios, as each scenario's limits state.
- Praxis is alpha. Its configuration can change between releases, so the pin and the rendered configuration are
  qualified together.
- Each client gets one more NetworkPolicy rule and one more connection. Walkthroughs and GIFs recorded against the
  current UIs may need a re-check; the demo-recording sessions are told which clients change.

## Security considerations

- **New reach:** one namespace that holds the Anthropic and Codestral keys and reaches the local models, MaaS and Redis.
  Ingress is limited to the experience-client namespaces, the UnifAI multiagent pods and the workstation entry.
- **Identity:** no shared secret is given to a client. Every call carries the `zuno` JWT, and is checked by the
  gateway or by the token-proxy's client credential.
- **Supply chain:** the image is built from a pinned commit of a public repository and pinned by digest. There is no
  signature (ADR-0620).

## Operational considerations

- `make d2 install praxis` / `make d2 uninstall praxis` and the switch `zuno_praxis_enabled`.
- Removal is safe: clients keep their default connection when the list is empty.
- Every cluster step needs the owner's go.

## Work packages

- [WP-292](../roadmap/work-packages/wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md) (namespace,
  allow-lists, chart, configuration).
- Clients, one each:
  - [WP-296](../roadmap/work-packages/wp-296-give-open-webui-the-alternative-gateways.md) (Open WebUI)
  - [WP-297](../roadmap/work-packages/wp-297-give-kagent-the-alternative-gateways-through-the-token-proxy.md) (kagent)
  - [WP-298](../roadmap/work-packages/wp-298-run-claude-code-on-sovereign-models-through-praxis.md) (Claude Code)
  - [WP-299](../roadmap/work-packages/wp-299-give-unifai-the-alternative-gateways.md) (UnifAI)
  - [WP-300](../roadmap/work-packages/wp-300-give-dify-the-alternative-gateways.md) (Dify)
  - [WP-301](../roadmap/work-packages/wp-301-give-openclaw-the-alternative-gateways.md) (OpenClaw)
  - [WP-302](../roadmap/work-packages/wp-302-give-the-blender-add-on-the-alternative-gateways.md) (Blender)
  - [WP-303](../roadmap/work-packages/wp-303-give-world-model-the-alternative-gateways.md) (world-model)
- [WP-304](../roadmap/work-packages/wp-304-write-the-multi-gateway-claude-code-and-agents-scenarios.md) (scenarios).

## Update 2026-11-17 (WP-292 spike): JWKS over https, and the client token never reaches a backend

The spike ([evidence](../roadmap/evidence/wp-292-praxis-spike.md)) ran upstream Praxis AI 0.11.0 on the workstation. It
settles two points of clause 4.

- **JWKS over https.** Praxis's JWT plugin refuses an `http://` JWKS URL. The alternative gateways therefore read the
  JWKS from the https Keycloak route, `https://keycloak.<domain>/realms/zuno/protocol/openid-connect/certs`, which the
  `zuno-ai-gateways` EgressFirewall allows, and not from the in-cluster `zuno-service.zuno-auth.svc` named in clause 4.
- **The client token never reaches a backend.** Praxis forwards the client's `Authorization` header unless a `headers`
  filter removes it. The Praxis configuration removes `authorization` and `x-api-key` at the start of every routing
  step, before any provider credential is injected.

The spike also counted many JWKS fetches. The fetch rate is measured in WP-292 before Praxis serves an audience.


## Update 2026-11-17 (owner request): one model, "Zuno wesh", on the default gateway, to compare with Praxis

Clause 1 (Zuno stays the default, its routing is not changed) is lifted by the owner's request for **one** change, and
only this one. Open WebUI lists the model `praxis.qwen3.5-9b-wesh` through Praxis, and the owner wants the same model
through the default path, next to "Zuno Code", to compare the two side by side.

- The ai-gateway declares a second model alias, `zuno-wesh=wesh:Zuno wesh`
  (`toolMarker.modelTaskAliases`, ADR-0596). It selects the task `wesh` of the client `open-webui`, whose
  `models.preferred` is the role `specialized` (the wesh fine-tune). The routing itself is generated from the agents
  release, as for `zuno-code`. Nothing else of the default gateway changes: quotas, floors, guardrails and the other
  models are as they were.
- The comparison found the cause of the odd symbols the owner saw on `praxis.qwen3.5-9b-wesh`, and it is not Praxis.
  The wesh export carries no sampling defaults, so a client that sends none (Open WebUI) sampled at temperature 1.0
  over the whole vocabulary: 6 answers of 32 held CJK tokens on vLLM itself, 0 of 32 with temperature 0.7, `top_k` 20
  and `top_p` 0.95. The fine-tune also never closes the template's `<think>`, so the reasoning parser filed the answer
  under `reasoning`. The models chart now sets `--override-generation-config` and
  `--default-chat-template-kwargs '{"enable_thinking":false}'` on this model, as it already did for `qwen3.5-9b`.

## Update 2026-11-18 (WP-292): a SaaS model gets no tools and no tool results through Praxis

The Consequences keep the C3 rule by sending only C1 content through an alternative gateway. Open WebUI turns the Zuno
tools on in every chat (`DEFAULT_MODEL_METADATA`), on its `praxis.*` models too, and that tool connection is C2
(ADR-0594): Confluence and the technical docs. Through the default gateway, a turn that used a C2 tool stays on local
models (signed markers and floors). Praxis has neither. On 2026-11-17 Anthropic happened to refuse such calls, because
it rejects tool names that contain a dot (`confluence.page.search`). Renaming the tools in Praxis would have sent C2
tool results to Anthropic, so the owner chose a refusal (2026-11-18).

- Praxis refuses, on its SaaS route (`claude`, `codestral-latest`), a call that offers tools (`tools`, or the legacy
  `functions`), or whose messages carry a tool call or a tool result, in Chat Completions or Anthropic Messages form.
  The answer is a 403 with code `saas_tools_not_allowed` and a message that tells the user to turn the tools off for
  the chat or to pick a local model. A call without tools passes, and the sovereign models keep their tools.
- The rule is an OPA step of Praxis's own policy (`gitops/charts/praxis/files/saas-no-tools.rego`), so it holds for
  every client of the gateway. A request whose body the policy did not receive is refused too
  (`saas_request_unreadable`).
- In Open WebUI, `praxis.claude` and `praxis.codestral-latest` answer once the Zuno tools are off for the chat.
  Removing the tools from these two models in Open WebUI, so that the refusal never shows, needs a per-model setting
  that the chart does not have yet. It is left for after the 2026-11-24 demo.

## Update 2026-11-19: the SaaS models of Praxis get no Zuno tools in Open WebUI

The owner asked on 2026-11-19 for the tools to be off for these two models rather than renamed (renaming would need
Praxis code and would undo the refusal above). The `open_webui` role now writes one Open WebUI model entry per SaaS
model of Praxis (`praxis.claude`, `praxis.codestral-latest`), from inside the Open WebUI pod
(`ansible/roles/open_webui/files/model_overrides.py`). The entry's `toolIds` is an empty list, which Open WebUI keeps
over the global default. The entry stays public, and nothing else in it changes. The ids come from the SaaS names
of the Praxis chart. The refusal stays in Praxis for every other client. The same day, the Claude model of both
gateways became `claude-sonnet-5-5` (the ai-gateway's `claude-3-5-sonnet-latest` was retired).

## Amended (2026-11-20): Praxis budgets on the ai-gateway subscription

A dated note, not a rewrite. Since 2026-11-20, Praxis is no longer a second MaaS consumer with its own `<model>-praxis` subscription on the local models: its ServiceAccount is
a second user of the `<model>-ai-gateway` subscription ([ADR-0570](0570-slim-the-ai-gateway-by-delegating-quotas-keys-and-exposure-to-maas.md) note of the
same date, [WP-314](../roadmap/work-packages/wp-314-fit-the-maas-gateway-wasm-config-under-1-4-mb.md)). The two ServiceAccounts keep separate counters of the same size. A Praxis 429 falls back to the direct step by design, so a Praxis client
does not see a MaaS 429. The SaaS routes of Praxis (Claude and Codestral) are unchanged.
