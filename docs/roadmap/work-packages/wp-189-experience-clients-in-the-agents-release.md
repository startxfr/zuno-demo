# WP-189: Experience clients in the agents release

- **State:** Repo work in review (2026-11-02: both repositories; the agents release, its promotion and the mcp-gateway roll wait for the user)
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
