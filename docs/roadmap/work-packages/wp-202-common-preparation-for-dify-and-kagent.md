# WP-202: Common preparation for Dify and kagent

- **State:** Not started
- **ADRs:** [ADR-0601](../../adr/0601-inject-client-credentials-tokens-for-experience-clients-without-oidc-passthrough.md), [ADR-0599](../../adr/0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md), [ADR-0600](../../adr/0600-govern-kubernetes-read-tools-in-the-mcp-gateway-and-admit-kagent-as-a-thin-operations-client.md), [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Depends on:** none
- **Related:** [WP-203](wp-203-dify-preparation.md), [WP-206](wp-206-kubernetes-read-tools-behind-the-mcp-gateway.md), [WP-207](wp-207-kagent-preparation-and-install.md), [WP-179](wp-179-common-preparation-for-experience-clients.md)
- **Target:** v0.14
- **Estimated files touched:** ~15 in `zuno-demo` (`components/zuno-token-proxy`, `gitops/charts/{namespaces,ai-gateway,keycloak}`, `Makefile`, Day 2 playbooks, `aap-config` DAGs, docs)

> Same role as WP-179 for v0.13: every shared file the Dify and kagent tracks would both edit is changed here, once, by one
> session. No cluster action except the build and roll of step 6, with the user's go.

## Goal

After this package, WP-204 and WP-207 only add files in their own directories.

## Steps

1. **Token proxy.** `components/zuno-token-proxy` per ADR-0601: two listeners (`/v1` to the ai-gateway, `/mcp` to the
   mcp-gateway), streaming and SSE passthrough, client-credentials token cached and refreshed at 70 % of its lifetime,
   `Authorization` and fixed headers overwritten, `503` without a token, `zuno_token_proxy_refresh_total{result}`.
   Tests: refresh, expiry, Keycloak down, header override, a streamed chat and an MCP `tools/list` against fakes.
   BuildConfig and signing like the other zuno components.
2. **Reusable chart piece.** A library template or small chart `gitops/charts/zuno-token-proxy` that WP-204 and
   WP-207 instantiate: Deployment, Service, ExternalSecret for the client secret, NetworkPolicy (ingress same namespace
   only).
3. **Namespaces.** `zuno-dify` and `zuno-kagent` in `gitops/charts/namespaces/values.yaml` with
   `zuno.io/experience-client: "true"`, default-deny, outside the mesh.
4. **ai-gateway values.** `experienceClients` gains `dify` and `kagent`; a new chart value `personaClaimClients`
   rendered as `PERSONA_CLAIM_CLIENTS` (today only a code default, `openclaw-*`, in `components/ai-gateway/app/auth.py`)
   gains both; `toolMarker.failClosedClients` gains both. Neither goes into
   `trustedPlatformClients`.
5. **Make and AAP.** `dify` and `kagent` in `DAY2_RUN_COMPONENTS`, the Day 2 install, check and uninstall playbooks and
   both AAP Day 2 DAGs, with no-op stub roles `ansible/roles/{dify,kagent}` that say "not implemented (WP-204/WP-207)".
6. **Build and roll** the token proxy image once, after the user's go; it is not deployed anywhere yet.
7. **v0.14 band.** `v0.14` in `ADR_VERSIONS` (`platform/docs/check_docs.py`), the by-version row, `## v0.14` in
   `versions.md`, the tracker phase. (Done with the ADRs on 2026-11-04.)

## Acceptance

`make d2 install` and `make d2 check` stay green with the stubs; the token proxy suite passes; `check_docs.py` is green.
