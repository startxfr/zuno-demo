# ADR-0043: Use standard MCP protocol behind the Zuno MCP Gateway

- **Status:** Implemented - see `components/mcp-gateway/app/downstream.py` (streamable-HTTP `mcp` SDK), `components/mcp-gateway/requirements.txt` (`mcp==2.0.0`), `tests/test_mcp_protocol.py`. sales-db and confluence (`components/mcp-servers/confluence/`, migrated and live-verified 2026-08-18 per ADR-0117/WP-02) speak real MCP behind the gateway; google-workspace/lucidchart/web-search MCP servers are still unimplemented (tracked under ADR-0326).
- **Target:** v0.1
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The project currently exposes a Zuno-specific `POST /v1/tools/{tool}/invoke` interface and JSON-RPC-like payloads. The long-term goal is to make MCP integrations reusable and standards-based while retaining central Zuno authorization and governance.

## Decision

Keep the Zuno MCP Gateway as the policy enforcement layer, but use a standards-compliant MCP SDK/protocol between the gateway and MCP servers. Where practical, the Agent Runtime should also consume a standard MCP client abstraction while the gateway injects policy enforcement transparently.

## Consequences

MCP servers become reusable by other compatible clients, protocol maintenance is reduced, and custom policy remains centralized.

## Security considerations

Protocol compliance must not allow clients to bypass the Zuno policy gateway. Network/workload controls from ADR-0037 remain mandatory.

## Operational considerations

Introduce compatibility tests against the selected MCP SDK and migrate servers incrementally.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Implementation state, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- [ADR-0037](0037-protect-mcp-servers-with-network-and-workload-identity-boundaries.md)
