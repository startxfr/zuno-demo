# ADR-0322: Migrate from Llama Stack configuration to the OpenShift AI OGX Operator

- **Status:** Partially implemented - DSC migration, health checks, OGX provider/parity tests, and (2026-08-21) a real live corpus proof through `zuno-ogx` are all merged and live; only the deliberately-deferred side-by-side provider-parity run (an operator/user scheduling decision, not a technical blocker) is still open, see the 2026-08-21 "Corpus proof" note below.
- **Target:** v0.1
- **Date:** 2026-08-11
- **Decision owners:** Zuno Demo architecture team
- **Supersedes:** [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md) and [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md) for OGX product mapping and implementation lifecycle

## Implementation note (2026-08-19)

`zuno-ogx` (the actual OGX Operator data-plane server, previously blocked
entirely) went live and healthy on the cluster:
`DeploymentReady`/`ServiceReady`/`HealthCheck` all `True`, `GET /v1/health`
returns `{"status":"OK"}`, real PostgreSQL/pgvector connection confirmed
(`Vector extension version 0.8.2` against the live `ogx` database).
Getting here required finding and fixing three independent, real upstream
bugs in the OGX operator (3.5.0-ea.2 / `github.com/ogx-ai/
ogx-k8s-operator` + `github.com/ogx-ai/ogx`), each confirmed by reading
the operator's actual source and verified live, not guessed: (1) its
OCI-manifest-fetch client (`pkg/config/oci_fetcher.go`) is anonymous-only
by design and never performs the registry auth challenge, so no registry
(`registry.redhat.io`, an internal zuno-ai-build mirror, even a real
public `docker.io` image) can ever satisfy it - worked around with
`spec.overrideConfig`, the CRD's own documented full-config bypass; (2)
`pkg/config/provider.go`'s `expandPgvectorProvider()` never sets a
`persistence` field for `remote::pgvector`, crashing the server at
startup (`AttributeError: 'NoneType' object has no attribute 'backend'`)
- the CRD's typed `PgvectorProvider` field has no way to supply one
either, so the whole typed `spec.providers` path is unusable for
pgvector; (3) `vector_stores.default_embedding_model`/
`default_reranker_model` are validated against
`registered_resources.models` and crash startup if referenced without a
matching registration - at the time, removed entirely rather than fixed
(see the 2026-08-21 corpus-proof note below for why that had to be
revisited). `files/ogx-override-config.yaml.tpl` is a full hand-authored
config.yaml (real distribution-starter content, trimmed to the real
`zuno-vllm`/`zuno-pgvector` providers with real Helm-templated connection
values); the pgvector password is injected via
`spec.workload.overrides.env`. The server being healthy was a necessary
precondition, not the finish line - the corpus proof and live
provider-parity run were still open.

## Implementation note (2026-08-21) — network path

Attempted the corpus proof (index/query a controlled test corpus through
the live `zuno-ogx` server) and hit a real, fourth architecture gap before
any indexing could run: `zuno-ogx`'s `zuno-vllm` inference provider is
configured (`gitops/charts/openshift-ai/values.yaml`'s `ogxServer.
vllmEndpoint`) to reach `http://embeddings-predictor.zuno-ai-run.svc:8080`
for embeddings, but `gitops/charts/models/templates/networkpolicy-
embedding.yaml`'s `embeddings` NetworkPolicy in `zuno-ai-run` only
allow-lists ingress from `rag-service` pods in `zuno-data` and
KFP-component pods in `zuno-ai-build` - `redhat-ods-applications` (where
`zuno-ogx` runs) is not in that list. Confirmed live: a curl from inside
the current `zuno-ogx` pod to that Service times out; the identical call
from `rag-service`'s own pod (an allow-listed source) is not itself
provably broken by this policy. `zuno-ogx`'s own `/v1/models` and
`/v1/vector_stores` both return empty lists, consistent with an OGX
deployment that has never successfully called out for an embedding.

This is a real least-privilege NetworkPolicy doing its job, not a bug -
widening it is a security-boundary change this session's guardrails
correctly withheld without the operator's explicit approval, the same
posture ADR-0201's own 2026-08-18 note took on its analogous
mesh-injection question.

**Operator decision (2026-08-21):** widen the whole `redhat-ods-applications`
namespace, not just the `zuno-ogx` pod - RHOAI's own operator manages that
namespace's pod labels, not this chart, so a namespace-wide rule is more
maintainable than tracking OGX's pod labels across operator upgrades.
`gitops/charts/models/templates/networkpolicy-embedding.yaml`'s
`embeddings` NetworkPolicy gained a `redhat-ods-applications`
namespaceSelector ingress rule; `helm lint`/`helm template` verified
before commit. Live reconciliation confirmed: a curl from inside a fresh
`zuno-ogx` pod to `embeddings-predictor.zuno-ai-run.svc:8080/v1/models`
now returns a real 200. Closing the network path surfaced two more real
bugs, in order.

## Implementation note (2026-08-21) — model registration

`POST /v1/vector_stores` itself calls `ogx/core/stack.py`'s
`validate_vector_stores_config()`, which resolves
`vector_stores.default_embedding_model` against
`registered_resources.models` **even for the raw `/v1/vector-io/insert`
+`/v1/vector-io/query` path with caller-supplied embeddings** - the
2026-08-19 note's "removed entirely" fix for the reranker-validation
crash had left `registered_resources.models: []`, which made every
vector store creation fail (`"Model 'None' not found"`), not just OGX's
own file-search/embed-at-rest convenience layer this was scoped around
avoiding. Confirmed by reading `ogx/core/stack.py`'s
`_validate_embedding_model()`/`_validate_reranker_model()` directly
inside the running container: the reranker validator only runs `if
default_reranker_model is not None`, so registering exactly one
embedding model (`bge-small-en-v1.5` via `zuno-vllm`) and setting
`vector_stores.default_embedding_model` to match - while leaving
`default_reranker_model` unset - closes the vector-store-creation gap
without reopening the reranker crash. Live-tested before commit (server
dry-run apply), then verified by tracking the actual GitOps deploy: fresh
pod, 0 restarts, `GET /v1/models` lists the registered model.

## Implementation note (2026-08-21) — vLLM endpoint /v1 suffix

With a model registered, vector store creation succeeded and
`/v1/vector-io/insert` worked immediately (`204`) - but
`/v1/vector-io/query` and `/v1/vector_stores/{id}/search` both 404'd.
The pod's own logs showed why: querying makes OGX embed the caller's
*query text* internally via its OpenAI-compatible client
(`openai/resources/embeddings.py`), and that internal call was what
404'd, not the outer route. `ogxServer.vllmEndpoint` was
`http://embeddings-predictor.zuno-ai-run.svc:8080` (no `/v1`) - the
OpenAI SDK appends `/embeddings` directly to `base_url`, assuming it
already ends in `/v1` (standard convention). Confirmed live:
`POST .../8080/embeddings` → 404, `POST .../8080/v1/embeddings` → 200.
Insert never hit this path (the caller already supplies the embedding),
which is why it worked before this fix and made the query-side bug easy
to miss. Fixed by appending `/v1` to the configured endpoint.

## Corpus proof (2026-08-21) — succeeded

With all three fixes live (NetworkPolicy, model registration, `/v1`
suffix), ran the actual corpus proof end to end against the live
`zuno-ogx` server: embedded two real documents via the real
`embeddings-predictor` service (same contract `rag-service`'s own
`app/embeddings.py` uses), created a vector store, inserted the embedded
chunks with real ADR-0046-shaped metadata (`classification`, `language`,
`product`, `version`, `acl_groups`), then queried by text
("How do I size a GPU for OpenShift AI?"). The query embedded the text
internally, ran the vector search, and returned the correct chunk with
every metadata field preserved exactly as inserted (title, source,
product, version, language, classification, `acl_groups` as a real
array) - this is the acceptance criterion "an OGX-backed RAG proof can
index/query a controlled test corpus through PostgreSQL/pgvector",
proven live, not mocked.

Also confirmed, as a useful side effect: OGX's OpenAI-shaped
`/v1/vector_stores/{id}/search` convenience endpoint rejects the same
request with a `400` (`attributes.acl_groups` must be a flat
string/number/boolean, not an array) - direct evidence that ADR-0322's
own design choice to route this through the raw vector-io API rather
than that convenience layer was correct, not just cautious: the
convenience layer literally cannot represent RAG's real ACL-array
metadata shape.

**Still open, unchanged from the 2026-08-19 note**: the side-by-side
live provider-parity run (the same real corpus through both OGX and
pgvector, diffed) remains a deliberately deferred operator/user
scheduling decision, not a technical blocker - `test_provider_parity.py`
already proves the two providers' row-mapping functions agree
structurally, and this note now additionally proves OGX's real backend
round-trips real metadata correctly.

## Context

The repository currently configures:

```yaml
llamastackoperator:
  managementState: Managed
```

and older documentation describes OGX as a project-level name for a collection of OpenShift AI capabilities rather than a discrete component.

Red Hat OpenShift AI 3.5 documents a **Llama Stack to OGX migration** and exposes the OGX Operator as a `DataScienceCluster` component activated with:

```yaml
spec:
  components:
    ogx:
      managementState: Managed
```

The OpenShift AI 3.5 OGX documentation exposes native agentic/RAG APIs, OpenAI-compatible APIs and vector-store integrations. PostgreSQL with pgvector is supported as a remote vector store provider, which aligns directly with ADR-0015 and avoids introducing another persistent vector database solely for OGX.

The Zuno architecture still needs an application orchestration boundary because OKF, C1/C2/C3 policy, MCP authorization, task-specific workflows and model-cost/policy decisions are Zuno responsibilities rather than OGX responsibilities.

## Decision

Adopt the **actual Red Hat OpenShift AI OGX Operator** as the product-native agentic/RAG capability and remove the legacy `llamastackoperator` configuration from the Zuno `DataScienceCluster`.

The integration boundary is:

```text
OKF agent contract
      |
      v
Zuno Agent Runtime
      |
      +--> LangGraph/LangChain when deterministic Zuno workflow orchestration is required
      |
      +--> Zuno RAG provider interface
                |
                +--> existing PostgreSQL/pgvector provider
                +--> OGX-backed provider
                          |
                          +--> OGX APIs
                          +--> PostgreSQL/pgvector remote vector store
      |
      +--> MCP Gateway / tools
      |
      v
Zuno AI policy routing / OpenShift AI MaaS
      |
      v
KServe / vLLM / llm-d / approved external models
```

### v0 migration scope

- replace `llamastackoperator` with `ogx.managementState: Managed` in the OpenShift AI `DataScienceCluster` configuration;
- add Day 1 health checks proving the OGX Operator/component is reconciled;
- correct platform documentation so OGX is no longer described as an informal umbrella term;
- preserve the current custom RAG provider and existing Tekos behavior during migration;
- preserve LangChain/LangGraph as an optional orchestration implementation behind the Agent Runtime, not as a competing platform operator.

### v0.1 integration scope

- implement the OGX-backed RAG provider behind the stable Zuno retrieval contract;
- use the existing PostgreSQL/pgvector platform as the preferred durable remote vector store where the current OpenShift AI support/lifecycle is acceptable;
- evaluate OGX OAuth, ABAC and multi-tenancy capabilities without bypassing Keycloak/Zuno authorization boundaries;
- add parity/evaluation tests before any task switches from the custom provider to OGX by default.

## Consequences

The repository aligns with the actual OpenShift AI 3.5 product model and can demonstrate a native Red Hat agentic/RAG capability without abandoning Zuno's declarative OKF contract or policy/orchestration differentiation.

There will be temporary duplication between the custom `rag-service` and OGX. This is intentional until evaluation proves equivalent retrieval, citations, metadata filtering and authorization semantics.

Because the targeted OpenShift AI 3.5 release train is Early Access and some OGX sub-capabilities can carry Technology Preview lifecycle status, Zuno must retain the provider abstraction and must not make the demo irreversibly dependent on a preview-only interface.

## Security considerations

OGX authentication/ABAC is defense in depth, not a replacement for Zuno's trusted identity propagation, agent entitlement, MCP policy intersection or C1/C2/C3 restrictions.

Any OGX-backed retrieval path must preserve:

- initiating-user identity;
- source ACL and group filters;
- data classification;
- provenance and citations;
- external-model egress restrictions.

## Operational considerations

The OpenShift AI role/checks must verify `ogx` readiness after `DataScienceCluster` reconciliation. Provider selection must be observable so traces identify whether a request used native pgvector retrieval or OGX-backed retrieval.

The deployment documentation must record the lifecycle status of the OGX capabilities actually enabled on the target OpenShift AI release.

## Acceptance criteria

- `llamastackoperator` is absent from the rendered `DataScienceCluster`.
- `spec.components.ogx.managementState: Managed` is rendered and reconciles successfully.
- Existing Tekos tests continue to pass without requiring the OGX provider.
- An OGX-backed RAG proof can index/query a controlled test corpus through PostgreSQL/pgvector.
- Provider-parity tests prove metadata/ACL/classification/citation behavior before default-provider migration.

## References

- Red Hat OpenShift AI Self-Managed 3.5, **Working with OGX**, including Llama Stack to OGX migration and activation of the OGX Operator.
- Red Hat OpenShift AI Self-Managed 3.5, **Select and deploy a vector database**, including PostgreSQL with pgvector as an OGX remote vector store provider.
- Red Hat OpenShift AI Self-Managed 3.5 release notes for the lifecycle status of OGX sub-capabilities.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0005](0005-use-okf-v0-2-as-the-declarative-agent-definition-contract.md)
- [ADR-0009](0009-separate-agent-runtime-from-ai-inference-gateway.md)
- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md)
- [ADR-0018](0018-use-ogx-with-langchain-and-langgraph-for-agentic-workflows.md)
- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0039](0039-make-agent-runtime-execute-the-okf-agent-contract.md)
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md)
- [ADR-0114](0114-use-zuno-as-a-policy-router-in-front-of-openshift-ai-maas.md)
- [ADR-0050](0050-abstract-the-rag-backend-and-integrate-openshift-ai-ogx.md)
