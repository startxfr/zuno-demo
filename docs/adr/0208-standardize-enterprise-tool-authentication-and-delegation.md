# ADR-0208: Standardize enterprise tool authentication and delegation

- **Status:** Implemented - see `platform/bindings/tools/tool-bindings.yaml`, `components/mcp-gateway/app/bindings.py`.
- **Target:** v0.2
- **Date:** 2026-08-13
- **Decision owners:** Zuno Demo architecture team

## Context

The target tool catalogue spans Atlassian, Google Workspace, Salesforce and Workday. These systems do not all have the same identity model. Google Drive/Gmail/Calendar/Meet actions must preserve the user's personal Google authorization, while some enterprise integrations may use delegated user OAuth, service identities or provider-specific application credentials.

Tool authorization inside Zuno must remain separate from the credential used to execute the downstream call.

## Decision

Every physical tool binding declares an authentication mode independently from logical tool authorization:

- `delegated-user`: downstream action executes with the end user's delegated provider identity;
- `service-identity`: downstream action executes with a platform-managed service identity and must enforce the Zuno subject/role scope itself;
- `provider-delegated`: provider-specific on-behalf-of/delegation flow when supported and explicitly validated.

Use `delegated-user` for Google Workspace capabilities (Drive, Gmail, Calendar and Meet), extending ADR-0014. Zuno policy determines whether the agent/task is allowed to invoke `drive.*`, `gmail.*`, `calendar.*` or `meet.*`; Google OAuth/native ACLs independently determine which resources the user can actually read or modify.

Confluence/Jira, Salesforce and Workday bindings select the strongest supported identity mode during implementation, but the mode is explicit configuration and never inferred from the tool name. Where service identity is unavoidable, authorization filters must be applied server-side from the validated initiating user/role context.

Provider access tokens, refresh tokens and service credentials remain server-side and are never placed in OKF, prompts, browser storage or RAG content.

## Consequences

Agents reason only about capabilities and do not need to know OAuth mechanics. Google Workspace naturally preserves personal Drive/Gmail/Calendar/Meet permissions, while other providers can evolve authentication without renaming capabilities.

## Security considerations

A Zuno permission never expands native provider permission. Delegated tokens are scoped minimally and stored according to ADR-0042/secret-management decisions. Service identities must not expose provider-wide permissions directly to the model; the gateway/server enforces resource/subject scope before execution.

## Operational considerations

Audit records include initiating Zuno subject, logical capability, backend binding and authentication mode, but never token material. Re-authentication/consent failures are surfaced as actionable integration errors.

## Acceptance criteria

- Drive/Gmail/Calendar/Meet calls execute with the user's delegated Google identity.
- Removing a user's Google permission prevents access even when Zuno still allows the logical capability.
- Backend bindings declare authentication mode explicitly.
- No OKF document or RAG chunk contains downstream credentials/tokens.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Migration/evolution and Review evidence.

## Related ADRs

- [ADR-0013](0013-propagate-end-user-identity-through-agent-calls.md)
- [ADR-0014](0014-use-delegated-google-oauth-for-google-workspace-access.md)
- [ADR-0024](0024-use-vault-for-application-secrets.md)
- [ADR-0042](0042-use-opaque-browser-sessions-with-server-side-token-storage.md)
- [ADR-0116](0116-decouple-logical-tool-capabilities-from-physical-backend-bindings.md)
