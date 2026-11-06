# dify

Day 2 component `dify`: Dify, the no-code workflow canvas, a user experience over the governed chain
(ADR-0599, under ADR-0587's admission contract, reaching the gateways through the
token proxy of ADR-0601).

| Verb | Does |
|---|---|
| `make d2 install dify` | Seeds the Vault paths, applies the token proxy instance (`zuno-token-proxy-dify-d1`), the External Knowledge adapter (`zuno-dify-knowledge-d1`, WP-205; build it first with `make d2 build dify-knowledge`) and the Dify Application (`zuno-dify-d1`), waits for the pods. |
| `make d2 check dify` | Both Applications Synced and Healthy, running images equal to the digest pins, Dify reaches its token proxy and nothing else, the Route answers only through Keycloak. |
| `make d2 uninstall dify` | Deletes both Applications. Keeps the Keycloak client, the Vault paths, the databases and the S3 bucket. |

## Before the first install

1. `ansible/confidential.yml`: the four `zuno_dify_s3_*` values (bucket, region, access key, secret key) of the
   dedicated bucket. `make d0 install vault` then seeds Vault `zuno/dify/s3`.
2. The pushed repository carries the `dify` database (postgresql chart), the `dify` Keycloak client and the
   `zuno-dify` ingress allowance on `zuno-data`; the `postgresql`, `keycloak` and `namespaces` Applications must
   have synced them, and `make d0 install vault` has seeded `dify/postgresql-app` and `keycloak/dify`, **before**
   the Keycloak client reaches the realm (the realm import reads the secret at start).
3. The plugin install needs PyPI once: `-e dify_plugin_install_window=true` on the install, then run it again
   without the flag to close it (the EgressFirewall is part of the chart).

## What is not here yet

The model provider, the MCP tool provider, the External Knowledge base (WP-205) and the per-person accounts are
configured against the running Dify API by the next WP-204 step.

## Example applications (WP-208)

`files/apps/*.yml` are Dify DSL exports, imported by `files/configure.py` on every `make d2 install dify`, once per name
(an existing application is left alone, its knowledge base is re-attached if missing):

| File | Type | What it shows |
|---|---|---|
| `agent-zuno.yml` | Agent (`agent-chat`) | function calling on `auto`, the MCP tools `confluence.page.search` and `confluence.page.read`, the external knowledge base as context |
| `chatflow-doc-technique.yml` | Chatflow (`advanced-chat`) | Start, knowledge retrieval over "Zuno technical documentation", LLM, Answer; published |
| `workflow-recherche-confluence.yml` | Workflow | a topic goes through the MCP tool `confluence.page.search`, an LLM summarises; published |

Rules learned live: the MCP tools are named in a DSL by the **server identifier** (`zuno-mcp-gateway`), not the database
uuid; Dify drops the plain `dataset_ids` of an imported DSL, so the knowledge base is attached after the import; the
models are registered with `function_calling_type: tool_call` (checked through the token proxy and the ai-gateway), which
the Agent needs. To add an example, export an application from the console (without secrets), replace nothing
instance-specific except what is described here, and drop the file in `files/apps/`.
