# WP-189: Experience clients in the agents release

- **State:** Done (2026-11-02: agents v0.9.0 released and promoted, the mcp-gateway reads the clients layer, tool lists proven through Open WebUI; OpenClaw switches its agent header in its own track)
- **ADRs:** [ADR-0592](../../adr/0592-declare-experience-clients-in-the-agents-release-apart-from-agents.md)
- **Depends on:** [WP-181](wp-181-install-open-webui-on-demo333.md)
- **Related:** [WP-183](wp-183-install-openclaw-on-demo333.md), [WP-184](wp-184-three-experiences-demonstration.md)
- **Target:** v0.13
- **Estimated files touched:** zuno-demo-agents (schema, two validators, release packaging, tests, CI, two client
  declarations); zuno-demo (mcp-gateway loader and chain check, admission, mcp-gateway chart, Open WebUI values, docs)

> Decisions of 2026-11-02 (user): a new declaration type rather than agents or the front door; C1 on both connections,
> task `chat` limited to read-only C1 tools. OpenClaw's scope (same task and tools, groups consultant and sales) was
> confirmed by its own track.

## Steps

1. **zuno-demo-agents** (branch `feat/experience-clients`, PR to `devel`): schema
   `zuno-okf-experience-client-v0.3.schema.json`; `validate_okf_schema.py` and `validate_okf_bundle.py` read
   `experience-clients/` (name not an agent's, no knowledge, tools in the policy and within the classification);
   `okf_release.py` adds the optional clients layer to the corp artifact; tests
   (`platform/okf/tests/test_experience_clients.py`, release tests) and the CI step; `experience-clients/open-webui`
   and `experience-clients/openclaw`.
2. **zuno-demo**: `admit_okf_bundle.py` extracts the layer to `/okf/experience-clients` and validates the clients'
   tools; the mcp-gateway loads them (`EXPERIENCE_CLIENTS_DIR`, `kind: experience-client`, collision fails closed) and
   refuses them in delegation chains; tests in both places; Open WebUI's MCP connection sends
   `X-Zuno-Data-Classification: C1`.
3. **Release and promotion** (user): merge the PR, release, promote the release in zuno-demo (`agents.lock`).
4. **Roll** (user's go): build the mcp-gateway with the loader, re-run the mcp role so okf-fetch extracts the new
   release; re-apply Open WebUI for the C1 header; tell the OpenClaw track to switch on its agent header.

## Acceptance

On demo333, `/mcp` `tools/list` with `X-Zuno-Agent: open-webui`, `X-Zuno-Task: chat`, `X-Zuno-Data-Classification: C1`:
`consultant-02` and `sale-01` see the tools of the task their groups allow, and no C2 tool; a caller outside the
access groups is refused; the same through Open WebUI's tool list.

## Live results (demo333, 2026-11-02)

- zuno-demo-agents PR #28 merged, release `v0.9.0` (with 08's sxa-legacy change), promoted in zuno-demo (`0dbbb190`,
  `okf-corp@sha256:0ff7385a…`).
- mcp-gateway built on `e43da20d` (contains the loader), image `sha256:62dba725…`.
- **Trap:** the okf-fetch init container runs `admit_okf_bundle.py` from the `supply-chain-signer` image, built
  2026-10-23: the first pod on v0.9.0 had no `/okf/experience-clients`. Rebuilt `supply-chain-signer` (build 16,
  `b20fd6f0`, `sha256:84608310…`) and recreated the pod: `/okf/experience-clients/{open-webui,openclaw}` present, no
  load error. Any change to `admit_okf_bundle.py` that the runtime needs requires that image rebuilt.
- Through Open WebUI (Playwright sign-in, `/api/v1/tools/id/server:mcp:zuno-mcp/specs`, agent `open-webui`, task
  `chat`, C1): `consultant-02` and `sale-01` get `drive.document.search`, `gmail.message.read`,
  `diagram.generation.create`; `finance-01` gets the first two; `recrut-01` none. Same as the local dry run of the
  release, which also gave `openclaw`: consultant and sales entitled, other groups refused.
