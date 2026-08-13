# ADR-0207: Decouple logical tool capabilities from physical backend bindings

- **Status:** To be implemented
- **Target:** v2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

The central MCP Gateway is already the correct policy enforcement point, but `components/mcp-gateway/app/downstream.py` currently routes by hard-coded tool-name sets/handlers instead of treating the policy's backend/server identity as an executable binding. This couples stable agent behavior to today's server layout and makes it difficult to split or replace MCP servers without changing runtime code.

The target catalogue includes Confluence, Jira, Google Drive, Gmail, Salesforce, Calendar, Meet and Workday. Those logical capabilities must remain stable even if one physical MCP server later becomes several services, or an MCP implementation is replaced by a direct API adapter behind the same trusted gateway.

## Decision

Use stable logical tool identifiers as the contract consumed by OKF tasks and policy. Prefer the canonical naming form:

```text
<domain>.<resource>.<verb>
```

Examples include:

- `confluence.page.search`, `confluence.page.read`, `confluence.page.create`, `confluence.page.update`
- `jira.issue.search`, `jira.issue.read`, `jira.issue.create`, `jira.issue.update`, `jira.comment.create`
- `drive.document.search`, `drive.document.read`, `drive.document.create`, `drive.document.update`
- `gmail.message.search`, `gmail.message.read`, `gmail.message.send`
- `salesforce.opportunity.read`, `salesforce.opportunity.create`, `salesforce.opportunity.update`
- `calendar.event.read`, `calendar.event.create`, `calendar.event.update`
- `meet.meeting.read`, `meet.meeting.create`
- `workday.profile.self.read`, `workday.profile.self.update`, `workday.profile.any.read`

Introduce a platform backend-binding registry that resolves an authorized logical capability to its physical provider/endpoint/transport. OKF agent/task bundles contain logical capability IDs only. MCP server names, Kubernetes Services, URLs and provider-specific tool names belong to the binding layer.

The MCP Gateway continues to authorize **before** resolving/invoking the physical backend. Routing must use the policy/binding data rather than hard-coded Python tool lists.

During migration, existing names such as `search_confluence`, `list_drive_files`, `read_gmail` and `get_customer` may be maintained as explicit aliases, but new agent contracts use canonical logical IDs.

## Consequences

Physical MCP topology becomes replaceable without changing agent definitions. A single Google Workspace MCP server can initially implement Drive/Gmail/Calendar/Meet and later be split without modifying OKF.

The gateway needs binding validation, startup diagnostics and alias migration logic.

## Security considerations

Bindings are platform-controlled configuration and cannot be supplied by an agent or caller. Unknown/missing bindings fail closed. Backend responses retain source classification/local-only metadata so ADR-0035 model-routing controls remain enforceable.

## Operational considerations

Traces must record both the logical capability and resolved backend binding. Health checks validate that every enabled policy capability has exactly one valid active binding for the environment.

## Acceptance criteria

- Agent/task OKF contains no MCP Service DNS names or URLs.
- Changing the physical server for a logical capability requires only binding/deployment configuration, not agent/runtime behavior changes.
- MCP Gateway no longer requires hard-coded per-tool routing sets in `downstream.py`.
- Unknown logical capability or missing binding returns a deterministic denial/error without contacting an arbitrary backend.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0036](0036-enforce-the-complete-mcp-authorization-intersection-in-the-gateway.md)
- [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md)
- [ADR-0208](0208-standardize-enterprise-tool-authentication-and-delegation.md)
