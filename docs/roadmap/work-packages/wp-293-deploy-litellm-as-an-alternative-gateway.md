# WP-293: Deploy LiteLLM as an alternative gateway

- **State:** Not started
- **ADRs:** [ADR-0621](../../adr/0621-run-litellm-as-an-alternative-ai-gateway.md)
- **Depends on:** [WP-292](wp-292-deploy-praxis-ai-in-the-alternative-gateways-namespace.md)
- **Related:** [ADR-0619](../../adr/0619-run-praxis-ai-as-an-alternative-ai-gateway-next-to-the-default-zuno-ai-gateway.md)
- **Target:** v0.17
- **Estimated files touched:** to be estimated

## Goal

LiteLLM runs in `zuno-ai-gateways` under ADR-0619, as an entry of every client's `altGateways` list.

## Steps

Not started. The owner decides ADR-0621 clause 1 (identity) first. The steps follow WP-292, except for: a mirrored image instead of a build, a PostgreSQL database, and virtual keys held by zuno-token-proxy.

## Acceptance

To be written when the work package starts.
