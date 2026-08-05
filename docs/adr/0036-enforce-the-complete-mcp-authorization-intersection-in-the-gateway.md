# ADR-0036: Enforce the complete MCP authorization intersection in the gateway

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

`policies/tools/tool-policy.yaml` documents the intended authorization formula: agent declaration ∩ task rights ∩ user group rights ∩ classification ∩ platform policy. The policy file states that the MCP Gateway must enforce all five factors, but the implementation and agent definition stubs do not yet provide a reliable end-to-end enforcement path.

## Decision

Make the central MCP Gateway the mandatory policy enforcement point for tool invocation. It must validate the calling agent, active task, validated user groups, effective data classification and GitOps platform policy before forwarding a standard MCP call. Missing or invalid policy inputs cause denial.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

Tool authorization becomes centralized, explainable and testable. Agent Runtime remains responsible for selecting a tool, but cannot bypass platform authorization.

## Security considerations

The gateway must fail closed, emit an auditable denial reason without leaking sensitive data, and never allow a task to widen its parent agent tool declaration.

## Operational considerations

Add policy decision traces and negative tests for each independent factor of the intersection.

## Implementation state

**Implemented (2026-08-05).** `components/mcp-gateway/app/policy.py`'s
`evaluate()` now checks all five ADR-0011 factors instead of three. The two
newly-added ones read from a new `app/agent_declarations.py`
(`AgentDeclarationStore`), which loads the same `agents/<name>/agent.okf.md`
+ `tasks/*.md` OKF bundles (ADR-0038) baked into this service's own image
(`COPY agents ./agents` in `Dockerfile`, matching the existing `policies/`
pattern) - a separate, smaller loader than Agent Runtime's
`app/registry.py`, per this repo's established convention of duplicating
small parsing code across independently deployed services:

1. **agent_declaration** - `tool_name` must appear in the union of
   `allowed_tools` across every task the calling agent (`X-Zuno-Agent`)
   declares.
2. **task_rights** - `tool_name` must additionally appear in the specific
   calling task's (`X-Zuno-Task`) own `allowed_tools` - checked as an
   explicit second step even though, for a well-formed bundle, passing (2)
   implies passing (1), so a denial reason always names the more precise
   factor that actually failed (Security considerations: "emit an
   auditable denial reason").

`X-Zuno-Agent`/`X-Zuno-Task` are new required (not optional-with-default)
headers on `POST /v1/tools/{tool}/invoke`; a missing, unknown, or
non-declaring value denies the call (fail closed, per Security
considerations). `components/agent-runtime/app/clients/mcp_client.py`'s
`invoke_tool()` now requires `agent_name`/`task_name` params (no default)
and `app/graph/nodes.py`'s `tool_call_node` supplies
`agent_name="tekos", task_name="answer-technical-question"` - the task the
one live `/v1/agents/tekos/chat` route always executes.

This pass also surfaced and fixed a real, unrelated pre-existing bug:
`PolicyStore.reload()` (`policy.py`) was iterating `tool-policy.yaml`'s raw
parsed YAML directly (`for item in raw`) instead of its `tools:` list
(`raw.get("tools", [])`) - the file's actual top-level shape is
`{"tools": [...]}`, per its own header comment. Every real load therefore
raised `TypeError` and the policy store never loaded, meaning every tool
call failed closed regardless of any of the five factors. This had gone
uncaught because no test previously exercised `PolicyStore.reload()`
itself - `evaluations/tekos/security_checks.py`'s
`confluence_policy_is_c2_and_local_only` parses the same file
independently (`yaml.safe_load(...).get("tools", [])`), which is correct
but meant it could never have caught the gateway's own loader bug.

Consequence for `evaluations/tekos/scenarios.yaml`: scenario 18 previously
exercised `get_customer` succeeding via a direct-to-gateway call
unconnected to any agent context. With agent_declaration now enforced,
that call is correctly denied - no v0 agent (Tekos included) declares
`get_customer` (it belongs to Comage/Advantage/Arkos's future, still
placeholder, task set). Scenario 18 was changed to assert this denial
(`mcp_gateway_denied`, `expect_status: 403`) rather than worked around,
since it is the platform's real, correct v0 behavior post-fix, not a test
regression.

Two new negative tests in `evaluations/tekos/security_checks.py` cover the
ADR-0040 entitlement/business-role split using this same enforcement path
(`entitlement_without_business_role_denied_confluence`,
`business_role_without_entitlement_denied_by_bff`); this ADR's own
acceptance coverage is scenarios 12/13/18 (`mcp_gateway_denied`,
`mcp_gateway_unknown_tool`) plus the direct `policy.py` unit-level checks
exercised during implementation (agent_declaration denial, task_rights
denial, unknown agent denial, missing-declaration denial).

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0010
- ADR-0011
- ADR-0022
- ADR-0043

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
