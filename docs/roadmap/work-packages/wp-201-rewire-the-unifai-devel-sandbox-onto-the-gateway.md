# WP-201: Rewire the unifai-devel sandbox onto the gateway

- **State:** Not started
- **ADRs:** [ADR-0598](../../adr/0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md)
- **Depends on:** WP-198
- **Related:** [ADR-0562](../../adr/0562-authenticate-unifai-against-the-zuno-keycloak-realm.md)
- **Target:** v0.13
- **Estimated files touched:** ~4 in the fork's examples

> Why: on `unifai-devel` the operator examples (demo-* LLMs and workflows, Gemini templates) are owned by `admin`, so no
> persona sees them. Two of the LLMs need an external key. User decision of 2026-11-04: keep it as a sandbox, rewired onto
> zuno-gateway and owned by ai-ops-01, with the zuno templates.

## Goal

ai-ops-01 on `unifai-ui-unifai-devel` sees the examples, and they run without any external API key.

## Steps

1. Confirm the realm and `adminUsers` of the devel stack.
2. In the fork's examples:
   - set `owner: ai-ops-01`;
   - move the LLMs onto the gateway config;
   - replace the Gemini templates with the zuno ones;
   - remove `demo-gemini` and `demo-openai`.
3. Re-apply them on demo333. This is a cluster action and needs the user's go.

## Acceptance

- As ai-ops-01 on `unifai-ui-unifai-devel`, the examples are listed and one workflow answers.
