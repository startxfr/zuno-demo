# WP-201: Rewire the unifai-devel sandbox onto the gateway (amended: keyless, isolated)

- **State:** Repo work in review
- **ADRs:** [ADR-0598](../../adr/0598-give-every-persona-default-unifai-team-workspaces-and-a-shared-catalog.md)
- **Depends on:** WP-198
- **Related:** [ADR-0562](../../adr/0562-authenticate-unifai-against-the-zuno-keycloak-realm.md)
- **Target:** v0.13
- **Estimated files touched:** ~4 in the fork's examples

> Why: on `unifai-devel` the operator examples (demo-* LLMs and workflows, Gemini templates) are owned by `admin`, so no
> persona sees them. Two of the LLMs need an external key. User decision of 2026-11-04: keep it as a sandbox, rewired onto
> zuno-gateway and owned by ai-ops-01, with the zuno templates.

## Goal

ai-ops-01 on `unifai-ui-unifai-devel` sees the examples, and they run without any external API key (mock LLM).

## Steps

1. **Confirm the identity.** Done on 2026-11-04: the live stack is on realm `zuno` with `adminUsers: [ai-ops-01]` and
   reads groups through oidc-claims. The 25 `demo-*` objects were owned by `admin`, the CRD default, which no realm user
   is.
2. **Variant A, chosen by the user on 2026-11-04.** The gateway variant would have needed the ai-gateway and mcp-gateway
   NetworkPolicies opened to `unifai-devel`; they only admit `zuno-unifai`. The fork gets a kustomize overlay,
   `examples/overlays/unifai-devel-demo333`, sent as a patch to the fork session:
   - every object gets `owner: ai-ops-01`;
   - it drops `demo-gemini`, `demo-openai`, `demo-vllm` and `demo-docs-wide`;
   - the two templates run on the mock LLM and the demo MCP server, with no placeholders;
   - `stack-unifai-devel.yaml` is refreshed to the live identity.

   The generic examples, used by the e2e tests, are left unchanged.
3. **Re-apply on demo333.** Delete the `admin`-owned objects, then
   `oc kustomize --load-restrictor LoadRestrictionsNone examples/overlays/unifai-devel-demo333 | oc apply -n unifai-devel -f -`.
   This is a cluster action and needs the user's go.

## Acceptance

- As ai-ops-01 on `unifai-ui-unifai-devel`, the examples are listed and one workflow answers.
