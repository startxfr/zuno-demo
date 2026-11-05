# WP-205: Dify External Knowledge adapter over the mcp-gateway

- **State:** Done 2026-11-05 on demo333 (commit 8a35dc8a): `zuno-dify-knowledge` built and signed in-cluster (digest sha256:71940d3f…), `zuno-dify-knowledge-d1` Synced and Healthy, External Knowledge API and base "Zuno technical documentation" registered in Dify (the registration probe passed). Evidence: Dify `external-hit-testing` returned 5 records for each of 4 queries, Confluence SXSI chunks kept `classification` C2 and docs.redhat.com chunks C1, with source URL and score; adapter logs show `POST /retrieval` 200 through the token proxy. Not exercised: a space the `dify` persona's groups do not allow (no such space identified; the filter is UnifAI's server-side ACL, the adapter adds none), and a knowledge node in a Dify workflow typed in the UI.
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
