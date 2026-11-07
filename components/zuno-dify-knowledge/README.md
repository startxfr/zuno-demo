# zuno-dify-knowledge

ADR-0599, WP-205. Dify's knowledge-retrieval node calls an **External Knowledge API**; this is that
API. It holds no store and no copy: each retrieval is one MCP `tools/call knowledge.tech.search`
(alias `search_technical_docs`) sent through the `zuno-token-proxy` of the namespace, so the caller is
the `dify` experience client and the group ACL (ADR-0568), the classification (ADR-0594) and the audit
stay the mcp-gateway's. Deployed by `gitops/charts/zuno-dify-knowledge`.

| Path | |
|---|---|
| `POST /retrieval` | `{knowledge_id, query, retrieval_setting:{top_k, score_threshold}}` -> `{"records":[{content, score, title, metadata:{source, classification, id}}]}` |
| `/healthz`, `/readyz`, `/metrics` | local, no key |

- **Auth.** Only `Authorization: Bearer <static key>` (Vault `dify/knowledge-api`); missing or malformed -> `403` code 1001, wrong -> `403` code 1002.
- **Probe.** Empty `knowledge_id` and `query` (Dify's registration probe) -> `200 {"records": []}`, no upstream call. Unknown `knowledge_id` -> `404` code 2001.
- **Filtering.** `top_k` is passed to the tool (capped by `MAX_TOP_K`); `score_threshold` is applied here, the tool has none.
- **Failure.** Gateway down, denied or tool error -> `502`, never an empty success. Nothing the persona's groups do not allow comes back: an empty list is a real answer.
- **Classification.** Kept as sent by the gateway; a chunk with none is reported `C2` (fail closed, as the gateway).

| Env | Meaning |
|---|---|
| `API_KEY` or `API_KEY_FILE` | the static bearer (required) |
| `MCP_URL` | default `http://zuno-token-proxy:8080/mcp` |
| `TOOL_NAME` | default `knowledge.tech.search` |
| `KNOWLEDGE_BASES` | `id=tag,...`, default `tech=knowledge.tech` |
| `MAX_TOP_K`, `UPSTREAM_TIMEOUT_S` | optional |
| `PROXY_KEY_FILE` | optional (WP-225 lot C): the token proxy's inbound key, sent as a bearer to `MCP_URL` |

Tests (token proxy / gateway faked):

    cd components/zuno-dify-knowledge && python3 tests/test_dify_knowledge.py

Build: `make d2 build dify-knowledge` (`ansible/roles/dify_knowledge_build`). Registered in Dify by `make d2 install dify` (`configure.py` step 5).
