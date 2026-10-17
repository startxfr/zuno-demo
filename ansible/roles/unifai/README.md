# unifai

Day 2 component (ADR-0561, ADR-0574, WP-151): the UnifAI agent and RAG platform.

- `zuno-unifai-d0` installs unifai-operator from its pinned catalog
  (CatalogSource + Subscription) - unless a Subscription for the package
  already exists on the cluster (demo333 runs one created by hand: it is
  detected and never duplicated).
- `zuno-unifai-d1` renders the `UnifaiStack` in `zuno-unifai` (identity on
  realm `zuno`, user-token forwarding, remote embedding, hybrid search), the
  shared ai-gateway LLM, the mcp-gateway MCP provider, signed OKF bundles and
  RAG sources.

Cluster-specific values come from `ansible/confidential.yml`
(`zuno_unifai_values`, deep-merged over the role's defaults), e.g. pinned
images, admin users, `okf.bundles`, `ragSources`, `stack.backup`.
The OKF public key is read from `agents/zuno-platform-signer.pub`.
