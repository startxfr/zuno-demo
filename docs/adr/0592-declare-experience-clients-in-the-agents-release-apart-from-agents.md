# ADR-0592: Declare experience clients in the agents release, apart from agents

- **Status:** Implemented (2026-11-02, WP-189: agents release v0.9.0 promoted, clients loaded by the mcp-gateway, tools proven live for open-webui and openclaw)
- **Target:** v0.13
- **Date:** 2026-11-02
- **Decision owners:** Zuno Demo architecture team
- **Related:** [ADR-0587](0587-admit-additional-user-experiences-over-the-one-governed-backend.md), [ADR-0588](0588-serve-a-general-purpose-chat-experience-with-open-webui.md), [ADR-0589](0589-serve-per-persona-openclaw-assistants-via-claw-operator-behind-a-token-injecting-egress-proxy.md), [ADR-0571](0571-evaluate-the-rhoai-mcp-gateway-before-extending-mcp-gateway.md), [ADR-0581](0581-derive-stack-configuration-from-the-admitted-corp-bundle.md), [ADR-0403](0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md)

## Context

ADR-0588 and ADR-0589 have Open WebUI and OpenClaw call the mcp-gateway with the user's token under a logical agent
name (`X-Zuno-Agent: open-webui`, `openclaw`), "entitled per group like any agent". The mcp-gateway only knows the
agents of the admitted zuno-demo-agents release (`/okf/agents`), and an unknown name gets an empty tool list.

Declaring the two clients as agents in that release has side effects nobody wants (WP-181 mapping, 2026-11-02):
`generate_stack_config.py` turns every agent, `placeholder` included, into a UnifAI bundle and a Keycloak `agent_*`
group, and every active agent into MaaS subscriptions; the a2a-gateway serves every active agent; any agent can be a
delegation target; the agent schema requires UI, model and `agent_*` entitlement fields, while a
client serves every employee through their business groups.

Data classification matters too: Open WebUI and OpenClaw chat at C1, so a SaaS model may answer. A tool that needs C2
(Confluence, Git, AAP, Salesforce) must not feed such a chat. The MCP connections sent no classification, so the
gateway applied its `/mcp` default, C2.

## Decision

**An experience client is declared in the agents release as its own document type, read only by the mcp-gateway.**

1. **Declaration.** `experience-clients/<name>/client.okf.md` in zuno-demo-agents, schema
   `zuno-okf-experience-client-v0.3`: `type: experience-client`, `zuno.name` (the logical agent name), `zuno.tasks`
   (ordinary task files, only `allowed_tools` read), `zuno.access.groups` (business groups), optional
   `zuno.classification`. No prompts, graph, RAG, model preference, UI tile, delegation or `VERSION`.
2. **Checks in the agents repository.** A client's name is no agent's; its tasks allow no knowledge; every tool is in
   the tool policy and reachable at the client's classification.
3. **Release.** The clients ship in an optional `application/vnd.zuno.okf.clients.v1.tar+gzip` layer of the signed
   corp artifact, never as agent artifacts or index entries, so no reader of agents sees them.
4. **Admission and runtime.** `admit_okf_bundle.py` extracts the layer to `/okf/experience-clients` and refuses a
   client whose tools are not served or whose name is an agent's. The mcp-gateway loads it
   (`EXPERIENCE_CLIENTS_DIR`) into the declarations under `kind: experience-client`: the access groups and the task's
   tools apply as for an agent, then the tool policy as always. A name collision fails the load closed. A client is
   never part of a delegation chain.
5. **Classification.** Both clients declare C1 and send `X-Zuno-Data-Classification: C1` on their model and MCP
   connections. Their task `chat` allows the read-only C1 tools `list_drive_files`, `read_gmail` and
   `generate_diagram`. Confluence and the technical knowledge base stay with the agents, on local models.
6. **Unchanged.** No UnifAI bundle, Keycloak group, MaaS subscription, A2A endpoint or routing entry is derived from
   a client; `generate_stack_config.py` does not read them.

> **Correction (2026-11-03, ADR-0594):** decision 5 is amended in part. The two clients keep declaring C1 on their model
> connection, but call the mcp-gateway at C2, and their task `chat` also allows `confluence.page.search`,
> `confluence.page.read` and `knowledge.tech.search`. Signed classification markers on the tool results make the
> ai-gateway answer those turns with local models only.

## Alternatives considered

- **Front door without `X-Zuno-Agent`:** works today (the `frontdoorCapabilities` ceiling, filtered by groups), but the
  tool set is the mcp-gateway's deployment value, not a reviewed policy per client, and it includes C2 tools.
- **Regular agents with `status: placeholder`:** still produce bundles, groups and A2A endpoints; every reader would
  have to learn to skip them, and one forgotten reader widens access.

## Consequences

- Adding or changing a client's tools is an agents release plus a promotion, like an agent's.
- A release without the layer declares no client; older releases are admitted unchanged.
- The mcp-gateway reads the clients at pod start (okf-fetch): a promotion rolls it.

## Security considerations

The client declaration can only narrow: the tool policy still applies to every call, with the caller's groups and the
declared classification. A client cannot delegate or be delegated to, so it never widens an agent's chain.

## Operational considerations

`tools/list` on `/mcp` with `X-Zuno-Agent: open-webui`, `X-Zuno-Task: chat` and a persona token shows the client's
surface; an empty list for an entitled persona means the release with the client is not admitted, or the mcp-gateway
has not restarted since the promotion.
