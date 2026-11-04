# WP-205: Dify External Knowledge adapter over the mcp-gateway

- **State:** Not started
- **ADRs:** [ADR-0599](../../adr/0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md)
- **Depends on:** [WP-203](wp-203-dify-preparation.md) step 6, [WP-204](wp-204-install-dify-on-demo333.md)
- **Related:** [WP-208](wp-208-five-experiences-demonstration.md)
- **Target:** v0.14
- **Estimated files touched:** `components/zuno-dify-knowledge` (code, tests, BuildConfig), its templates in `gitops/charts/dify`

## Goal

Dify's knowledge-retrieval node returns the same group-filtered, classification-marked chunks as the
`search_technical_docs` tool, without any store in `zuno-dify`.

## Steps

1. Implement `POST /retrieval` (contract from WP-203 step 6): `knowledge_id` maps to a fixed tag (`knowledge.tech`),
   `query` and `retrieval_setting.top_k`/`score_threshold` map to the tool's arguments; the call goes to the token
   proxy `/mcp` as `tools/call search_technical_docs`; each result becomes a record (`content`, `score`, `title`,
   `metadata` with source URL and classification).
2. Authenticate Dify with a static key from Vault (Dify only sends a bearer); refuse anything else.
3. Tests against a fake mcp-gateway; build and sign in-cluster.
4. Register the External Knowledge API and one knowledge base in Dify from the role.

## Acceptance

A Dify knowledge node returns a Confluence chunk the `dify` persona's groups allow, and nothing for a space they do
not; the chunk keeps its classification.
