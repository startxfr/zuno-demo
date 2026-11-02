# WP-180: Open WebUI preparation

- **State:** Not started
- **ADRs:** [ADR-0588](../../adr/0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0587](../../adr/0587-admit-additional-user-experiences-over-the-one-governed-backend.md)
- **Depends on:** [WP-179](wp-179-common-preparation-for-experience-clients.md) (its interfaces only; this spike can start once they are written)
- **Related:** [WP-181](wp-181-install-open-webui-on-demo333.md), [WP-182](wp-182-openclaw-preparation.md)
- **Target:** v0.13
- **Estimated files touched:** one evidence file `docs/roadmap/evidence/wp-180-open-webui-spike.md`; no shared file

> Track Open WebUI. Runs in parallel with WP-182 under WP-179's coordination protocol. No cluster action except, with the
> user's go, a throw-away pod in a labelled scratch namespace.

## Goal

Answer the questions ADR-0588 leaves open, so WP-181 is pure assembly.

## Steps

1. **Version and pins.** Pick the chart and application version (≥ v0.6.31 for native MCP); record the chart version, the
   image digests (main image and any sidecar), and the licence of that version.
2. **User token to the ai-gateway.** Read the source of the pinned version: can an OpenAI connection send the signed-in
   user's OAuth access token as `Authorization`, and is it refreshed? If not, specify the header relay (session token in,
   bearer out, same namespace, first-party, signed in-cluster) and its interface.
3. **MCP connection.** Can an MCP server connection carry the user's token and fixed headers (`X-Zuno-Agent: open-webui`,
   `X-Zuno-Task`)? Test against the mcp-gateway `/mcp` from a scratch pod with a persona token: `tools/list` returns only
   the persona's tools.
4. **OpenShift.** Render the chart with the `restricted-v2` SCC in mind: security context left unset, writable paths,
   volume, probes. List the values to override.
5. **Switches off.** The exact environment variables or admin settings that disable RAG, upload, web search, image
   generation, community functions, pipelines, user-added connections and local sign-up; whether they can be locked
   from configuration (not only from the admin UI).
6. **Keycloak.** The client's settings (redirect `/oauth/oidc/callback`, scopes, groups claim mapper, admin group).

## Acceptance

The evidence file answers steps 1 to 6 with sources and test output, states "relay needed" or "no relay", and lists
every value WP-181 will set.
