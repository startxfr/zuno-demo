# Agent Evaluations

Each initial agent receives 20 evaluation scenarios. The initial acceptance target is 75%.

`make d2 test`/`make d2 stresstest` (ADR-0057/ADR-0058) run availability
checks and aggregate this content against a live cluster on demand - see
`docs/adr/0057-*.md`/`0058-*.md`.

## Running against UnifAI

UnifAI serves the agents (ADR-0561) and is the only evaluation target since
WP-156 retired the legacy agent stack. Every agent with evaluations (tekos,
arkos, comage, advantage, finage, naveo; cognos and soursage have none) runs its
`scenarios.yaml` through the UnifAI UI/MAS API (WP-154, WP-155 wave 0):

    cd evaluations/<agent>
    export UNIFAI_URL=https://<unifai-ui-route> DEMO_PERSONA_PASSWORD=...
    export UNIFAI_TEAM_NAME=agent-<agent>      # or UNIFAI_TEAM_ID; UNIFAI_WORKFLOW defaults to the agent name
    export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
    export EVAL_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/zuno-evaluations)
    python3 run_scenarios.py
    python3 security_checks.py
    python3 run_acceptance_gate.py             # scenarios + security + gate checks

`EVAL_CLIENT_SECRET` (the `zuno-evaluations` client) mints the persona tokens the
scenarios and checks send to the shared services they call directly (MCP gateway,
ai-gateway). `--target unifai`/`EVAL_TARGET=unifai` are still accepted; any other
target is refused.

The transport is shared: `common/unifai_target.py` (login, session, streamed run,
parametrised by agent; `tekos/unifai_target.py` re-exports it) and
`common/unifai_checks.py` (security-check factories). Scenarios and checks that
cannot apply to UnifAI are printed as skipped with the reason and left out of every
count, never counted as passes. For a `status: placeholder` agent (advantage,
finage, naveo) no workflow exists, so chat scenarios are skipped, the blocked-chat
scenarios pass when no workflow is exposed, and the identity check is skipped.
Offline tests: `pytest evaluations/tests`.

The exploratory `stress_test.py` batteries (tekos, arkos, comage) drove the
retired agent stack directly and were removed with it; `make d2 stresstest`
reports that layer as not run until a UnifAI port exists.
