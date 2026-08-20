# Arkos Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for Arkos
(ADR-0326/WP-31, the second real agent). `run_scenarios.py`/
`run_acceptance_gate.py` here are thin `AGENT=arkos` wrappers around the
canonical, shared implementation in `evaluations/tekos/` (ADR-0342 - see
that directory's `run_scenarios.py` module docstring for why the shared
code lives there rather than being copied per agent); `scenarios.yaml`,
`gate_config.yaml` and `security_checks.py` are Arkos's own, real content.

**Not yet wired into `make day1|d1 check agents`'s automatic path**
(`ansible/roles/agents/tasks/check.yml` only smoke-tests Arkos's frontend
`/healthz` today) - running this gate against a live cluster requires the
human scenario-review checkpoint WP-31's own brief gates on first. Once
that review has happened, the operator runs it explicitly:

```bash
cd evaluations/arkos
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://arkos.apps.<cluster-domain>
export ARKOS_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/arkos-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / SALES_DB_MCP_URL /
# AI_GATEWAY_URL default to their in-cluster Service DNS names - override if
# running this from outside the cluster via a port-forward instead. Reaching
# those in-cluster names at all requires running from a network location the
# ADR-0037/ADR-0052 NetworkPolicies actually allow, same constraint
# evaluations/tekos/README.md documents for its own gate Job.
python3 run_acceptance_gate.py     # scenarios + security_checks + gate_checks, one exit code
python3 run_scenarios.py           # just the 20 scenarios
python3 security_checks.py         # just the security-negative checks
```

`AGENT=arkos`/`TASK_NAME=draft-architecture-testimonial` are set by the
wrapper scripts automatically - only set them yourself if invoking the
canonical `evaluations/tekos/run_scenarios.py`/`run_acceptance_gate.py`
directly against this directory's `scenarios.yaml` for some other reason.

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters) - the exact same `type` vocabulary
`evaluations/tekos/scenarios.yaml` uses, since `run_scenarios.py`'s
handlers are generic HTTP call patterns, not Tekos-specific code.

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9 - 7 is DAT
drafting, 8 is workshop-presentation's latency, ADR-0514's kind-aware
draft path via the same shape, 9 is structure-demo's early-exit branch
over SSE, WP-6), DAT drafting folding in live Confluence context
alongside the RAG corpus (10-11, the
concrete proof of ADR-0326's "live Jira/Confluence actions without
physical endpoint coupling" bullet - Jira itself waits on its own MCP
server, not yet scheduled), MCP Gateway policy enforcement (12-13, 18),
model routing/classification fail-closed behavior (14-15,
config-consistency checks that don't need a live cluster), BFF JWT
validation (16-17), namespace isolation for the three still-genuinely-
placeholder agents (19), and service health (20).

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what a full
evaluation run requires.

## Security-negative checks

`security_checks.py` (same setup as above, run from this directory) checks
identity-propagation, classification and entitlement behavior that isn't
part of the fixed 20-scenario acceptance count: the BFF actually forwards
the caller's token to the Agent Runtime, the Runtime ignores a forged
`user_sub` in the request body rather than treating it as authoritative,
Confluence's canonical `confluence.page.search`/`.read` capabilities are
correctly classified C2 with `external_model_policy.allow_context: false`
(a config-only check, no live cluster needed), `X-Zuno-Local-Only: true`
actually forces `components/ai-gateway` to pick the local provider even
for a C2 request that would otherwise be SaaS-eligible, the two-dimension
group model is enforced server-side in both directions using two new
fixture personas mirroring Tekos's own (`arkos-entitlement-only-user-01`:
`agent_arkos` entitlement but no business role, denied `confluence.page.search`
by the MCP Gateway with 403; `consultant-role-only-user-01`: `consultant`
business role but no `agent_arkos` entitlement, denied by the BFF itself
with 403 before the request ever reaches the Agent Runtime - ADR-0349
moved Arkos's audience from board to the consultant tier, so the shared
consultant fixture now carries this converse case), and a direct call to
`sales-db-mcp` that bypasses the MCP Gateway entirely is denied by the
server itself (401) - a platform-wide (ADR-0037), not Arkos-specific,
boundary this gate still verifies.
