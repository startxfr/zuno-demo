# Agent Evaluations

Each initial agent receives 20 evaluation scenarios. The initial acceptance target is 75%.

`make d2 test`/`make d2 stresstest` (ADR-0057/ADR-0058) run availability
checks and aggregate this content against a live cluster on demand - see
`docs/adr/0057-*.md`/`0058-*.md`.

## Running against UnifAI (`--target unifai`)

Every agent with evaluations (tekos, arkos, comage, advantage, finage, naveo;
cognos and soursage have none) runs the same `scenarios.yaml` through the UnifAI
UI/MAS API instead of agent-runtime/the BFF (WP-154, WP-155 wave 0):

    cd evaluations/<agent>
    export UNIFAI_URL=https://<unifai-ui-route> DEMO_PERSONA_PASSWORD=...
    export UNIFAI_TEAM_ID=<the agent's team workspace id>   # UNIFAI_WORKFLOW defaults to the agent name
    python3 run_scenarios.py --target unifai
    python3 security_checks.py --target unifai
    python3 run_acceptance_gate.py --target unifai          # scenarios + security + gate checks

The transport is shared: `common/unifai_target.py` (login, session, streamed run,
parametrised by agent; `tekos/unifai_target.py` re-exports it) and
`common/unifai_checks.py` (security-check factories). Scenarios and checks that
cannot apply to UnifAI are printed as skipped with the reason and left out of every
count, never counted as passes. For a `status: placeholder` agent (advantage,
finage, naveo) no workflow exists, so chat scenarios are skipped, the blocked-chat
scenarios pass when no workflow is exposed, and the identity check is skipped.
`EVAL_TARGET=unifai` is equivalent to the flag. Offline tests:
`pytest evaluations/tests/test_unifai_target.py`.
