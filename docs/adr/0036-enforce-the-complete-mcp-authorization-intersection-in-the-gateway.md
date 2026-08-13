# ADR-0036: Enforce the complete MCP authorization intersection in the gateway

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`policies/tools/tool-policy.yaml` documents the intended authorization formula: agent declaration ∩ task rights ∩ user group rights ∩ classification ∩ platform policy. The policy file states that the MCP Gateway must enforce all five factors, but the implementation and agent definition stubs do not yet provide a reliable end-to-end enforcement path.

## Decision

Make the central MCP Gateway the mandatory policy enforcement point for tool invocation. It must validate the calling agent, active task, validated user groups, effective data classification and GitOps platform policy before forwarding a standard MCP call. Missing or invalid policy inputs cause denial.

## Consequences

Tool authorization becomes centralized, explainable and testable. Agent Runtime remains responsible for selecting a tool, but cannot bypass platform authorization.

## Security considerations

The gateway must fail closed, emit an auditable denial reason without leaking sensitive data, and never allow a task to widen its parent agent tool declaration.

## Operational considerations

Add policy decision traces and negative tests for each independent factor of the intersection.

## Implementation state

**Implemented (2026-08-05).**

- `components/mcp-gateway/app/policy.py`'s `evaluate()` now checks all five ADR-0011 factors instead of three. The two newly-added ones read from a new `app/agent_declarations.py` (`AgentDeclarationStore`), which loads the same `agents/<name>/agent.okf.md` + `tasks/*.md` OKF bundles (ADR-0038) baked into this service's own image - a separate, smaller loader than Agent Runtime's `app/registry.py`, per this repo's convention of duplicating small parsing code across independently deployed services:
  1. **agent_declaration** - `tool_name` must appear in the union of `allowed_tools` across every task the calling agent (`X-Zuno-Agent`) declares.
  2. **task_rights** - `tool_name` must additionally appear in the specific calling task's (`X-Zuno-Task`) own `allowed_tools`, checked as an explicit second step so a denial reason always names the more precise factor that actually failed.
- `X-Zuno-Agent`/`X-Zuno-Task` are new required headers on `POST /v1/tools/{tool}/invoke`; a missing, unknown, or non-declaring value denies the call (fail closed). `components/agent-runtime/app/clients/mcp_client.py`'s `invoke_tool()` now requires `agent_name`/`task_name` params (no default) and `tool_call_node` supplies `agent_name="tekos", task_name="answer-technical-question"`.
- Bug found and fixed: `PolicyStore.reload()` was iterating `tool-policy.yaml`'s raw parsed YAML directly (`for item in raw`) instead of its `tools:` list, raising `TypeError` on every real load - the policy store never loaded, meaning every tool call failed closed regardless of any of the five factors. No prior test exercised `PolicyStore.reload()` itself.
- Consequence: `evaluations/tekos/scenarios.yaml` scenario 18 previously exercised `get_customer` succeeding via a direct-to-gateway call unconnected to any agent context. With agent_declaration now enforced, that call is correctly denied (no v0 agent declares `get_customer`) - scenario 18 was changed to assert this denial (`mcp_gateway_denied`, `403`) as correct v0 behavior, not a regression.
- Two new negative tests cover the ADR-0040 entitlement/business-role split using this same enforcement path (`entitlement_without_business_role_denied_confluence`, `business_role_without_entitlement_denied_by_bff`); this ADR's own acceptance coverage is scenarios 12/13/18 plus direct `policy.py` unit checks (agent_declaration denial, task_rights denial, unknown agent denial, missing-declaration denial).

## Evolution (2026-08-13)

ADR-0335 preserves this gateway as the authoritative tool-policy enforcement point but removes the remaining routing coupling between logical tool names and hard-coded downstream handlers. Authorization is evaluated on stable logical capabilities; a separate binding registry resolves an authorized capability to the physical MCP server/API implementation. The current hard-coded routing in `components/mcp-gateway/app/downstream.py` is therefore transitional implementation debt, not part of the durable contract.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0010](0010-introduce-a-central-mcp-gateway.md)
- [ADR-0011](0011-define-tool-authorization-as-policy-intersection.md)
- [ADR-0022](0022-use-gitops-managed-declarative-agent-tasks-and-policies.md)
- [ADR-0043](0043-use-standard-mcp-protocol-behind-the-zuno-mcp-gateway.md)
