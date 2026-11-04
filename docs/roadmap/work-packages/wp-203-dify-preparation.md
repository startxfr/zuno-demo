# WP-203: Dify preparation

- **State:** Done (2026-11-04: steps 1 to 8 answered live on demo333, scratch namespace removed; see [the evidence](../evidence/wp-203-dify-spike.md))
- **ADRs:** [ADR-0599](../../adr/0599-serve-a-no-code-workflow-canvas-with-dify-as-an-experience-client.md), [ADR-0601](../../adr/0601-inject-client-credentials-tokens-for-experience-clients-without-oidc-passthrough.md)
- **Depends on:** [WP-202](wp-202-common-preparation-for-dify-and-kagent.md) steps 1 and 3 (a local token proxy build is enough)
- **Related:** [WP-204](wp-204-install-dify-on-demo333.md), [WP-205](wp-205-dify-external-knowledge-adapter-over-the-mcp-gateway.md)
- **Target:** v0.14
- **Evidence:** [wp-203-dify-spike.md](../evidence/wp-203-dify-spike.md)
- **Estimated files touched:** one evidence file `docs/roadmap/evidence/wp-203-dify-spike.md`; no shared file

> No cluster action except, with the user's go, a throw-away install in `zuno-dify-scratch` that is removed afterwards.
> Not while demo333 is being upgraded.

## Goal

Answer the questions ADR-0599 leaves open, so WP-204 is pure assembly.

## Steps

1. **Version and pins.** `dify-helm` chart version, Dify version, every image digest (api, worker, beat, web,
   plugin-daemon, sandbox, agent-backend, local-sandbox), the licence text of that version.
2. **OpenShift.** Render with the bundled PostgreSQL, MinIO and vector database off. Which pods start under
   `restricted-v2` with the security context unset; writable paths; the plugin-daemon volume; whether the sandbox and
   local-sandbox can run, else how to switch them off cleanly.
3. **External services.** Dify against a scratch database in `zuno-postgresql` (or a throw-away PostgreSQL in the
   scratch namespace) and an in-namespace Redis; required env (`SECRET_KEY`, plugin-daemon keys, `DB_*`,
   `STORAGE_TYPE=opendal` on a PVC).
4. **Model provider.** The OpenAI-API-compatible plugin: can it be installed offline (bundled `.difypkg`) and
   preconfigured from env or API, not only from the UI? Does it send custom headers, or must the token proxy set them
   all? A chat through the proxy gives `zuno_model_tokens{client="dify"}`.
5. **MCP tool.** Dify's MCP tool provider against the mcp-gateway `/mcp` through the proxy: `tools/list` returns only the
   `dify` client's tools.
6. **External Knowledge.** The exact `/retrieval` request and response Dify 1.17 sends and expects, recorded from a stub.
7. **Switches off.** Datasets and upload, the marketplace, other provider plugins, code node, HTTP node to the internet,
   telemetry; which can be locked from configuration. Every outbound host Dify tries at boot.
8. **Login.** oauth2-proxy in front of the web and api Routes (paths `/console/api`, `/api`, `/v1`, `/files`, `/e/`);
   first-admin seeding; local sign-up off.

## Acceptance

The evidence file answers steps 1 to 8 with sources and test output and lists every value WP-204 will set. The scratch
namespace is gone.
