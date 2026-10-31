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
Every bundle is verified keyless (ADR-0578): the frozen Vault Transit
public key of the pre-release bundles was removed (WP-164, 2026-10-25).
Bundles normally come from the admitted release
(`zuno_unifai_released_bundles`); a bundle listed by hand in
`zuno_unifai_values.okf.bundles` needs `okf.verify.keyless` and
`okf.trustedRoot` too, or the chart refuses to render.
