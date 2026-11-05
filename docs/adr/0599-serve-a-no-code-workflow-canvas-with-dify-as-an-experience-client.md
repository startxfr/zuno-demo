# ADR-0599: Serve a no-code workflow canvas with Dify as an experience client

- **Status:** Implemented
- **Target:** v0.14
- **Date:** 2026-11-04
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0588](0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0590](0590-front-openclaw-with-oauth2-proxy-and-an-egress-firewall-one-claw-operator-per-persona-namespace.md), [ADR-0592](0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md), [ADR-0568](0568-adopt-unifai-rag-on-qdrant-with-hybrid-search-and-rhoai-embeddings.md), [ADR-0601](0601-inject-client-credentials-tokens-for-experience-clients-without-oidc-passthrough.md)

## Context

The three v0.13 experiences cover agents (UnifAI), general chat (Open WebUI) and personal assistants (OpenClaw). None
lets a business user **draw** an LLM workflow (a canvas of model, knowledge, tool and branching nodes) and publish it
as an app. Dify is the most used open-source product of that kind. Facts that shape the decision (2026-11-04):

- **No official Helm chart.** Dify's README points to the community chart `BorisPolonsky/dify-helm` (0.39.0, Dify
  1.17.0). That chart deploys api, worker, beat, web, plugin-daemon, sandbox and, in recent versions, agent-backend and
  local-sandbox, plus optional bundled PostgreSQL, Redis, MinIO and a vector database.
- **Licence:** a modified Apache 2.0. Running a multi-tenant service (more than one workspace) needs written permission,
  and the logo and copyright in the web console must stay.
- **Login:** the Community Edition offers email/password and GitHub or Google OAuth. OIDC and SAML SSO are Enterprise
  features.
- **Models:** an "OpenAI-API-compatible" provider plugin takes a base URL and a static key.
- **Knowledge:** Dify's own datasets (upload, chunking, embedding, vector store), or an **External Knowledge API**: Dify
  calls `POST <endpoint>/retrieval` with a static bearer key and gets back records with `content`, `score`, `title` and
  `metadata`.
- **Tools:** Dify 1.x can use an MCP server (streamable HTTP) as a tool provider.
- **OpenShift:** the chart has no `restricted-v2` profile. The code sandbox historically needs extra privileges
  (seccomp, chroot).

ADR-0587 forbids a client its own model key, RAG store or upload, and lets knowledge arrive only through MCP tools.

## Decision

**Dify is deployed as a single-workspace experience client under ADR-0587's contract.**

1. **Packaging.** Chart `gitops/charts/dify` wraps `dify-helm` at a pinned version, every image by digest. ArgoCD
   Application `gitops/apps/dify/`, role `ansible/roles/dify`, Day 2 run component `dify`. Namespace `zuno-dify`
   (label `zuno.io/experience-client: "true"`, default-deny, outside the mesh) declared in the `namespaces` chart.
   Pod security context left to `restricted-v2`, with no `anyuid` grant. A component that cannot run that way is
   switched off, not given a wider SCC.
2. **State.** Dify uses two databases, `dify` (api, worker, beat) and `dify_plugin` (plugin-daemon), owned by one role
   in the shared `zuno-postgresql` (PGO user and ExternalSecret, as for MLflow; WP-203). A Redis inside `zuno-dify`
   serves as cache and Celery broker only. File storage is a **dedicated S3 bucket** (user decision 2026-11-04; the
   platform's EBS volumes are ReadWriteOnce and the chart wants ReadWriteMany); the plugin-daemon keeps a small
   ReadWriteOnce volume for installed plugins. No MinIO, and no vector database is deployed.
3. **Login.** oauth2-proxy in front of the console Route (Keycloak client `dify`, allowed groups from the experience
   declaration), as in ADR-0590. Dify Community has no SSO and needs a local account to exist, so the install role creates
   **one local administrator** (user decision 2026-11-05, replacing the per-person accounts of 2026-11-04): its email and
   the shared demo password of ADR-0595 are kept in Vault `dify/admin`, and local sign-up is off. Everyone Keycloak admits
   works in the one workspace (licence) as that administrator and as the one persona identity (ADR-0601 decision 5).
4. **Models.** One OpenAI-API-compatible provider whose base URL is the `zuno-token-proxy` (ADR-0601) in front of the
   ai-gateway, with a dummy key. The model list is the ai-gateway's (`auto`, and `zuno-code` per ADR-0596). No other
   provider plugin is installed.
5. **Knowledge.** Dify datasets and upload are **unused and unreachable**: Dify has no switch to disable them (WP-203
   section 6), so no vector store and no embedding model exist, and the only knowledge base is the one below. One **External Knowledge** base points at `zuno-dify-knowledge`,
   a first-party adapter that implements `POST /retrieval` by calling the mcp-gateway `/mcp` tool `search_technical_docs`
   (through the token proxy, `X-Zuno-Agent: dify`). The adapter holds no store and no copy. Group ACLs (ADR-0568) and
   classification markers (ADR-0594) apply to the Dify identity exactly as to any other client.
6. **Tools.** One MCP tool provider, the mcp-gateway `/mcp` through the token proxy. The logical client `dify` is
   declared in the agents release (`experience-clients/dify`, ADR-0592) with its tasks, allowed tools and groups.
7. **Off.** The marketplace (`MARKETPLACE_ENABLED=false`) and plugin installation from the internet, provider plugins
   other than the one above (installed from a package whose sha256 is pinned, `langgenius/openai_api_compatible`
   0.0.73), the code sandbox and the code node (WP-203: the sandbox crashes under `restricted-v2`, so it stays off),
   the agent backend, web-search and HTTP nodes to the internet, telemetry and update checks. The EgressFirewall denies
   `0.0.0.0/0` apart from the Keycloak Route and the dedicated S3 bucket. The plugin daemon runs `uv sync` per plugin
   and needs PyPI: `pypi.org` and `files.pythonhosted.org` are allowed **only during the install window**, which the
   role opens for the install and closes again (user decision 2026-11-04).
8. **Exposure.** One Route with an ACME certificate, held by the oauth2-proxy. The Dify logo and copyright are kept.

## Alternatives considered

- **Dify datasets with the RHOAI embedding model:** the familiar upload-a-PDF demo, but a second knowledge store
  outside classification and the group ACLs, and a new `/v1/embeddings` route on the ai-gateway. Rejected.
- **MCP tools only, no External Knowledge:** no new component, but Dify's knowledge-retrieval node, the core of a
  canvas RAG demo, would stay empty. Rejected.
- **The guide's install** (bundled PostgreSQL, Redis and MinIO, `anyuid` on the namespace, a dummy key straight to
  vLLM): bypasses every gateway. Rejected.
- **Langflow or Flowise:** comparable canvases with OIDC in the community editions, but a smaller field footprint than
  Dify. Not retained for now. The admission pattern would be the same.

## Spike findings (WP-203, 2026-11-04)

The decisions above were checked on demo333 under `restricted-v2` with no SCC granted
([evidence](../roadmap/evidence/wp-203-dify-spike.md)). Beyond what changed above: the chart's nginx cannot write its
cache, so the repository ships its own nginx deployment on port 8080 with `emptyDir` volumes (same routing, from the
chart's own ConfigMap); the chart's own ExternalSecrets are `external-secrets.io/v1`, which this cluster does not
serve, so the pods read a Secret rendered by our own `v1beta1` ExternalSecret through explicit environment variables.

## Consequences

- Dify workflows can be shown next to UnifAI's: same models, guardrails, tools and knowledge, drawn by hand instead of
  declared in OKF.
- Calls are counted per persona (ADR-0601 decision 5), not per Dify user.
- A community chart is a supply-chain risk. It is pinned, rendered and reviewed on every bump, and nothing is pulled
  from the chart's repository at run time.

## Security considerations

The single workspace is a licence condition and also the security boundary: every Dify user acts with the `dify`
persona's rights. Who may sign in is decided by Keycloak groups at the oauth2-proxy. With the marketplace, the sandbox
and internet egress off, a workflow cannot run arbitrary code or reach outside the cluster.

## Operational considerations

`zuno_model_tokens{client="dify"}` and mcp-gateway audit lines with `agent=dify` are the proof of the governed path.
A Dify chat that answers while both stay empty means a bypass.
