# Naveo Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for
Naveo (ADR-0410/ADR-0307/WP-41, scaffolded from
platform/templates/agent/). `run_scenarios.py`/`run_acceptance_gate.py`
here are thin `AGENT=naveo` wrappers around the canonical, shared
implementation in `evaluations/tekos/` (ADR-0342); `scenarios.yaml`,
`gate_config.yaml` and `security_checks.py` are this agent's own content
(scaffolded skeleton - review/adjust scenario messages before the human
review checkpoint WP-41 gates on).

**Not yet wired into `make day2|d2 check agents`'s automatic path** -
running this gate against a live cluster requires the human
scenario-review checkpoint. Once that review has happened, the operator
runs it explicitly:

```bash
cd evaluations/naveo
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://naveo.apps.<cluster-domain>
export NAVEO_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/naveo-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
python3 run_acceptance_gate.py     # scenarios + security_checks + gate_checks, one exit code
python3 run_scenarios.py           # just the 20 scenarios
python3 security_checks.py         # just the security-negative checks
```

`AGENT=naveo`/`TASK_NAME=answer-onboarding-question` are set by the
wrapper scripts automatically.
