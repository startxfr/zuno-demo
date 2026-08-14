# ADR-0117: Implement Confluence as the first real external MCP integration

- **Status:** Partially implemented - real MCP server, binding registry wiring, chart, build/deploy plumbing and protocol tests merged (`components/mcp-servers/confluence/`, `platform/bindings/tools/tool-bindings.yaml`, `gitops/charts/mcp-confluence/`); live Confluence Cloud verification pending (2026-08-14, roadmap WP-02)
- **Target:** v0.1
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team
- **Renumbered:** formerly ADR-0210, promoted from the v0.2 stream to v0.1 (2026-08-13 roadmap reorganization)

## Context

ADR-0116 already names stable logical capabilities for Confluence (`confluence.page.search`, `confluence.page.read`, `confluence.page.create`, `confluence.page.update`) and a binding-registry mechanism to resolve them to physical backends. ADR-0205 already decides that indexed `knowledge.tech` content (which already includes ingested Confluence pages, per ADR-0330) is the normal semantic read path, and live Confluence MCP is reserved for freshness-sensitive reads and all writes. ADR-0208 already requires an explicit, non-inferred authentication mode per binding. ADR-0043's own status line records that only the sales-db MCP server is real today; `components/mcp-servers/confluence/` is README-only, and `mcp-gateway/app/downstream.py` currently serves every `search_confluence` call from an in-process demo handler returning two hardcoded fake results.

None of this needs a new architecture decision - it needs a first real implementation, the same role ADR-0330 played for `knowledge.tech` ingestion ("the first physical implementation... not the definition of RAG architecture for every agent").

## Decision

Build a real MCP-protocol server in `components/mcp-servers/confluence/` (mirroring `components/mcp-servers/sales-db/`'s real implementation shape: MCP SDK server, gateway-token-authenticated, parameterized tools), implementing exactly the four capabilities ADR-0116 already named: `confluence.page.search`, `confluence.page.read`, `confluence.page.create`, `confluence.page.update`.

Replace `mcp-gateway/app/handlers/confluence.py`'s demo-mode handler by wiring `app/downstream.py` to resolve these capabilities through ADR-0116's binding-registry mechanism rather than adding another hardcoded tool-name entry - this is also the first real consumer proving that binding layer exists and works, alongside ADR-0342 proving the Agent Runtime side of the same generalization.

Authentication mode is `service-identity` (ADR-0208), using the `zuno/confluence/technical` Vault credential (email + API token) already wired this session via `ansible/roles/vault/tasks/install.yml`. The MCP Gateway's existing `policy.evaluate()` continues to authorize the caller's agent/task/role/classification *before* invoking this shared service identity, satisfying ADR-0208's requirement that service-identity bindings enforce Zuno subject/role scope themselves rather than relying on the downstream credential to do so.

Retrieval behavior follows ADR-0205 exactly: normal technical questions are answered from `knowledge.tech` (ADR-0330's already-ingested Confluence content, unchanged by this ADR); this live MCP path is invoked only when the caller explicitly needs current state or is performing a write. Both paths share the same `acl_groups`/`technology` metadata conventions ADR-0330/ADR-0202 already define - this ADR does not introduce a second, parallel Confluence ACL model.

## Consequences

Zuno gains its first working example of the full target chain - Agent Runtime -> MCP Gateway -> logical tool -> backend binding -> real MCP server -> external API - validating ADR-0116's architecture against a real integration instead of only sales-db's simpler, internal-database-backed case. The same binding/server pattern becomes the template for Jira, Google Workspace and Salesforce as ADR-0326's agent rollout needs them.

## Security considerations

Agent Runtime never learns the Confluence server URL or credential - both stay behind the MCP Gateway's binding resolution and Vault-sourced secret, per ADR-0116/ADR-0024. User identity and audit information (initiating subject, agent, task, logical capability, resolved binding, authentication mode) are preserved through the full call chain per ADR-0208's operational requirement, without ever logging token material. Writes require an explicit write capability separate from read (ADR-0340's read/write separation already applies to Confluence); read access never implies write access.

## Operational considerations

Traces distinguish indexed-knowledge answers from live-Confluence-verified answers per ADR-0205's "no silent source substitution" requirement. A failed live Confluence call is surfaced as an explicit tool error, not silently downgraded to a stale indexed answer presented as current.

## Acceptance criteria

- `confluence.page.search`/`read`/`create`/`update` execute against real Confluence Cloud through the MCP Gateway, not the demo handler.
- A task can retrieve `knowledge.tech` context, then separately read a live Confluence page and write/update it, in one exercised chain (extended to `knowledge.project` once ADR-0209 lands in v0.2).
- Agent Runtime and OKF task definitions contain no Confluence server URL, credential, or vendor-specific tool name - only the four logical capability IDs.
- `mcp-gateway/app/downstream.py` resolves these capabilities via binding data, not a new hardcoded tool-name entry.
- An end-to-end acceptance test covers the full chain; the demo-mode Confluence handler is removed once the real implementation passes it.
- `docs/adr/0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md`'s status line is updated in place to record Confluence as migrated, once this ADR's acceptance criteria are met (procedural follow-up, not part of this ADR's own decision).

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
- [ADR-0205](0205-prefer-indexed-knowledge-for-read-and-live-tools-for-freshness-and-write.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
- [ADR-0340](0340-extend-business-role-authorization-with-cdp-and-scoped-capabilities.md)
- [ADR-0209](0209-introduce-project-scoped-agent-memory.md)
