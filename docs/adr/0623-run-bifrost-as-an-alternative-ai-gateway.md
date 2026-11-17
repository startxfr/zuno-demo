# ADR-0623: Run Bifrost as an alternative AI gateway

- **Status:** Proposed
- **Target:** v0.17
- **Date:** 2026-11-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md) (the frame for alternative AI gateways)

## Context

Bifrost is the fourth alternative gateway, added by the owner to the shortlist (2026-11-17).

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Virtual keys carry budgets, token and request limits, model allowlists and MCP tool filters. Teams and customers have budgets. Business-unit and user budgets, and identity-provider tokens, are Enterprise. | docs.getbifrost.ai `/features/governance/virtual-keys`, read 2026-11-17 |
| F2 | Routing rules are CEL expressions over model, headers, virtual key, team, customer and budget use. Their actions are weighted targets, ordered fallbacks, and a TTFT cutoff. | docs.getbifrost.ai `/providers/routing-rules.md`, read 2026-11-17 |

## Decision

**Bifrost is deployed under ADR-0619 with one virtual key per client, held by zuno-token-proxy, unless the owner
chooses an Enterprise trial.**

1. **Open: identity**, as in ADR-0621 clause 1.
2. **A CEL routing rule** on a classification header is shown as a comparison with the Zuno floors in the
   `multi-gateway` 15-minute scenario.

## Alternatives considered

None yet; to be written when the owner reopens it.

## Consequences

Per-person quotas are not available without a licence.

## Security considerations

Virtual keys are secrets held by the token-proxy, never by a client.

## Operational considerations

To be written with the work package.

## Work packages

[WP-295](../roadmap/work-packages/wp-295-deploy-bifrost-as-an-alternative-gateway.md) (not started).
