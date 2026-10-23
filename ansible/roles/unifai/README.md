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
Bundles listed by hand in `zuno_unifai_values.okf.bundles` are the
pre-release, Vault-Transit-signed ones (ADR-0564): they verify with
`files/zuno-platform-signer.pub`, the Transit public key frozen here when
`agents/` left the repository (WP-165). Nothing signs new bundles with it
any more; it is removed once `zuno_unifai_released_bundles` (keyless, from
the admitted release, ADR-0578) is the only path (WP-164).
