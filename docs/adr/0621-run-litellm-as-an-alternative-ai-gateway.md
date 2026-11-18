# ADR-0621: Run LiteLLM as an alternative AI gateway

- **Status:** Proposed
- **Target:** v0.17
- **Date:** 2026-11-17
- **Decision owners:** Zuno Demo architecture team
- **Extends:** [ADR-0619](0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md) (the frame for alternative AI gateways)

## Context

LiteLLM is the second alternative gateway in the owner's order (2026-11-17). It follows the frame of ADR-0619:
- `zuno-ai-gateways`;
- the `altGateways` client contract;
- sovereign models plus Claude and Codestral;
- the same Keycloak identity.

### Findings

| # | Finding | Evidence |
|---|---|---|
| F1 | Budgets and TPM/RPM limits per user, team, team member, key and customer are in the open-source proxy. All budgets need a database. Per-model budgets need an Enterprise licence. | docs.litellm.ai `/docs/proxy/users`, read 2026-11-17 |
| F2 | JWT/OIDC authentication (Keycloak) needs a LiteLLM Enterprise licence. | docs.litellm.ai `/docs/proxy/token_auth`, read 2026-11-17 |
| F3 | Fallback lists and OTLP export are in the open-source proxy. No routing or fallback span is documented. | docs.litellm.ai `/docs/proxy/logging`, read 2026-11-17 |

## Decision

**LiteLLM is deployed in `zuno-ai-gateways` as an alternative gateway under ADR-0619. How it receives identity is
decided before its work package starts.**

1. **Open: identity.** Two options, for the owner to decide:
   - (a) zuno-token-proxy holds one LiteLLM virtual key per client and maps the Keycloak identity to it. Budgets are
     then per client, not per person.
   - (b) an Enterprise trial for JWT. Not usable beyond its trial period.
2. **Its database** is a new PostgreSQL database on the platform's PostgreSQL. Its image is mirrored and pinned by
   digest (ADR-0612). It is not built from source.
3. **Its admin UI** (spend per team and key) is part of the `multi-gateway` 15-minute scenario.

## Alternatives considered

- **Build from source with the ADR-0620 pipeline.** Not needed: the published image carries the open-source features.

## Consequences

- One more database to back up.
- Identity is weaker than with Praxis unless the licence is bought.

## Security considerations

Virtual keys are secrets held by the token-proxy, never by a client.

## Operational considerations

To be written with the work package.

## Work packages

[WP-293](../roadmap/work-packages/wp-293-deploy-litellm-as-an-alternative-gateway.md) (not started).
