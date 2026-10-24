# WP-172: Gateway enforcement of the delegation chain

- **State:** Repo work merged
- **ADRs:** [ADR-0401](../../adr/0401-introduce-agent-delegation-limited-to-targets-an-agent-declares.md), [ADR-0403](../../adr/0403-propagate-the-users-identity-and-the-delegation-chain-across-a2a-calls.md), [ADR-0406](../../adr/0406-limit-agent-delegation-by-depth-cycle-and-budget.md)
- **Depends on:** [WP-170](wp-170-agent-delegation-contract-and-adrs.md), [WP-171](wp-171-okf-delegation-fields-and-conformance-cases.md)
- **Related:** [ADR-0011](../../adr/0011-define-tool-authorization-as-policy-intersection.md), [WP-146](wp-146-unifai-identity-and-context-header-forwarding.md)
- **Target:** v0.11
- **Estimated files touched:** ~8 in `components/mcp-gateway` (new `agent_chain.py`, `policy.py`, `main.py`, `agent_declarations.py`, `telemetry.py`, tests) and the evaluations

## Goal

The mcp-gateway verifies a delegation chain in the one evaluation path and refuses everything the contract refuses.

## Steps

1. `agent_declarations.py` (the OKF hook): read `delegation.targets` and the agent's status.
2. New `agent_chain.py` (not `delegation.py`, which is OAuth credential delegation): parse `X-Zuno-Delegated-By` and
   `X-Zuno-Delegation-Depth`; check the entry count, that each hop is a declared target of the previous agent, that
   every agent is `active`, no repeated agent, depth at most `min(max_depth, ceiling)`.
3. `policy.evaluate`: an optional chain context; the five factors apply to the target alone, on the classification its own
   header declares (ADR-0565; the level rises along the chain in the agents' runs, WP-173); the user must hold the target's `access.groups` (the `/mcp` check, REST path included
   for delegated calls); when `delegation.allow_write` is false, a tool whose `tool-policy.yaml` `access` is not `read` is refused on a delegated call.
4. `main.py` (REST and `/mcp`): read the headers; `telemetry.py` and the log line add `sub`, `delegated_by`, `depth`.
5. Tests per refusal (malformed, depth mismatch, undeclared target, inactive target, cycle, depth over the limit, user
   without the target group, write refused), plus conformance cases; run with the component venv, `OTEL_SDK_DISABLED=true`.

## Acceptance

Every refusal above is a test; a call without chain headers behaves exactly as before (the existing suites pass
unchanged); the audit line carries the chain.

## Progress (2026-10-24)

Done: `agent_declarations.py` (classification, targets, `max_depth`), `agent_chain.py` (parser, `DelegationLimits`,
`verify_chain`), `policy.py` (`access`, chain handling, the one `evaluate`), `main.py` (REST and `/mcp` read both
headers; a chain without an agent is refused), `telemetry.py` (`zuno.user_sub`, `zuno.delegated_by`,
`zuno.delegation_depth`), the audit line, `LIMITS_POLICY_PATH` in the Dockerfile and the chart, and
`tests/test_agent_chain.py` (21 tests: parsing, every refusal, REST and `/mcp`, the audit line). Every existing
gateway test still passes.

Decision recorded on the way: the classification is **not** derived or capped by the gateway. A first version refused a
delegated call above a delegator's `preferred_classification`; the real values (Tekos C1, Arkos C3) showed that this refuses
the demo case by construction, and ADR-0565 defines `preferred_classification` as the level a run *starts* at and then only
rises. The level is therefore carried and raised by the agents' runs (WP-173), and the gateway judges each call on its own
header. ADR-0401 and ADR-0403 say so.

Not live until a release carrying the OKF delegation fields and `access` is promoted (WP-171); before that no bundle
declares a target, so every delegated call is refused.

Decided when the records were accepted: the boolean `delegation.allow_write` is transitional. When approval ships (WP-173) the gateway check
becomes "the target `agent/task` is on `delegation.write_allowed`" (ADR-0409 clause 5), and this module's `DelegationLimits` and `evaluate`
change with it, in the same corp release.
