# ADR-0053: Make make check an end-to-end acceptance and security gate

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current check path is primarily service-health oriented. The project requires proof that the agent chain, classification, authentication, RAG, MCP and model routing behave correctly, not merely that pods answer `/healthz`.

## Decision

`make check` must run layered checks: infrastructure readiness, Keycloak login/claims, BFF and Runtime auth, RAG retrieval, MCP allow/deny, local model inference, permitted SaaS fallback, classification enforcement, SSE first token, citations, and the 20 Tekos evaluation scenarios. Security-negative cases are first-class acceptance tests.

## Consequences

The demo gains one operator command that proves business behavior and critical security assumptions. Checks may take longer but failures become actionable.

## Security considerations

Mandatory negative tests include unauthorized agent access, wrong group, forged user identity, direct MCP bypass, C2 Confluence to SaaS denial and missing/expired tokens.

## Operational considerations

Return machine-readable results and non-zero exit status when mandatory gates fail. Preserve the 75% quality threshold while making security checks 100% mandatory.

## Implementation state

**Implemented (2026-08-05)**: `make check` runs the full layered gate as one Ansible role (`ansible/roles/agents/tasks/check.yml` → `run_acceptance_gate.yml`) driving one Python orchestrator (`evaluations/tekos/run_acceptance_gate.py`).

- **Layering**: infrastructure readiness (existing OKF structural validation + frontend `/healthz`, kept as-is) → Keycloak login/claims, BFF/Runtime auth, RAG retrieval, MCP allow/deny, local model inference, classification enforcement, SSE first token and citations (`evaluations/tekos/scenarios.yaml`'s 20 fixed scenarios, ADR-0027/0028 - scenario 3 was extended to decode and assert the token's `groups` claim, not just that login succeeds) → permitted SaaS fallback (new `evaluations/tekos/gate_checks.py`, a config-consistency check against `platform/ai-gateway/provider-routing.yaml`, no live cluster needed, since proving a live SaaS fallback would require deliberately breaking the local model's availability).
- **Security-negative coverage**: `evaluations/tekos/security_checks.py` already covered five of six mandatory cases from earlier phases (business-role-without-entitlement/entitlement-without-business-role for "unauthorized agent access"/"wrong group", forged `user_sub` for "forged identity", the sales-db-mcp bypass for "direct MCP bypass", `X-Zuno-Local-Only` forcing local for "C2 Confluence to SaaS denial") and `bff_rejects_missing_jwt` covered "missing" tokens; the "expired" half was a genuine gap - no code here could construct a validly-signed expired token without a real Keycloak instance. Closed with new offline tests (`components/agent-runtime/tests/test_auth.py`, `components/mcp-gateway/tests/test_auth.py`): each mints its own RSA keypair, monkeypatches the JWKS client, and proves an expired-but-correctly-signed token and a well-formed token signed by an untrusted key are both rejected with 401. Both run and pass, wired into `lint.yml`'s `python` job.
- **Bug found and fixed**: the "direct MCP bypass" check only accepted a clean HTTP 401 as "denied"; once run from inside the cluster, a NetworkPolicy-level deny (a connection timeout, since ADR-0037/0052's policies never allow-list this test identity) would raise an unhandled exception and be misreported as an error rather than a pass. Fixed to treat either denial layer as a valid pass - the stronger, now-actually-exercised guarantee.
- **Machine-readable output**: `run_acceptance_gate.py` combines all three layers (20 scenarios at 75%, `security_checks.py` and `gate_checks.py` both at 100%) into one process, printing each module's existing human-readable tables plus one closing JSON line (`{"scenarios": {...}, "security_checks": {...}, "gate_checks": {...}, "overall": "PASS"|"FAIL"}`); exit code is non-zero unless all three gates pass.
- **Execution model**: most called services (`agent-runtime`, `mcp-gateway`, `ai-gateway`, `rag-service`) have no OpenShift Route, reachable only in-cluster (ADR-0023). New `run_acceptance_gate.yml` runs the gate as a one-shot Job in `zuno-ai` (same pattern as `sql_schema`), reading the Vault-issued demo-persona password and `tekos-frontend` client secret into a Job-local Secret, scripts delivered via ConfigMap on a `python:3.12-slim` image. This surfaced that ADR-0037/0052's precise per-workload NetworkPolicies mean an arbitrary test pod can't reach most of these services by design - rather than weaken any policy, the Job runs as a new, narrowly-scoped `acceptance-gate` workload identity, explicitly allow-listed in `gitops/charts/{agent-runtime,mcp-gateway,ai-gateway}` and a new `gitops/charts/tekos/templates/networkpolicy.yaml` (the BFF had none before). `rag-service` needed no change (`zuno-data`'s namespace-wide baseline already admits any `zuno-ai` pod). `sales-db-mcp` deliberately received no allowance, per the bypass-check fix above.
- **Pre-existing bug surfaced but not fixed here**: wiring `KEYCLOAK_URL` for the Job exposed that Keycloak's real hostname is `keycloak.<domain>`, while `gitops/charts/tekos/templates/_helpers.tpl`'s `keycloakIssuerUrl` and every `evaluations/tekos/*.py` script default to a `sso.<domain>` convention no Route in this repository creates. The Job uses the real hostname, so this ADR's own gate is unaffected, but the mismatch would break the live Tekos frontend's OIDC login on a real cluster - it belongs to ADR-0032/0033's already-Implemented identity plumbing, flagged here rather than silently patched as a drive-by fix to another ADR's closed state.
- **Not executed**: the Job has not run in a real cluster; `ansible-playbook --syntax-check` and `helm lint` passed for everything touched, and `gate_checks.py` plus both new `test_auth.py` files were actually executed and pass.

See [Standard clauses](README.md#standard-clauses) for Alternatives considered, Acceptance criteria and Review evidence.

## Related ADRs

- ADR-0027
- ADR-0028
- ADR-0030
- ADR-0032
- ADR-0035
- ADR-0036
- ADR-0045
