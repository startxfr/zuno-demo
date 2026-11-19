# AI Security

Controls include prompt-injection defenses, model/data classification enforcement, tool allow-lists, state-transition validation, response grounding, controlled web-search context and masked sensitive logging.

Where each control lives:

- **Prompt-injection defences**: guardrails in the ai-gateway ([ADR-0567](../adr/0567-move-trustyai-guardrails-into-the-ai-gateway.md), [guardrails scenario](../demo/scenarios/governance/guardrails.md)).
- **Model and data classification enforcement**: [ADR-0021](../adr/0021-route-models-according-to-c1-c2-c3-classification.md) and [ADR-0565](../adr/0565-derive-data-classification-from-okf-and-only-allow-raising-it.md) ([sovereignty scenario](../demo/scenarios/governance/ai-gateway-sovereignty.md)).
- **Tool allow-lists**: [ADR-0011](../adr/0011-define-tool-authorization-as-policy-intersection.md) ([MCP tools by group](../demo/scenarios/governance/mcp-tools-by-group.md)).
- **Threats and their closing decisions**: [threat model](threat-model.md).

