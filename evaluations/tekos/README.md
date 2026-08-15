# Tekos Evaluation

The 20 acceptance scenarios and the 75% pass-threshold report for Tekos,
the first functional agent. Since ADR-0342/WP-31, `run_scenarios.py`,
`run_acceptance_gate.py` and `gate_checks.py` here are the canonical,
shared implementation every real agent's own evaluation directory reuses
(see `evaluations/arkos/README.md` for the first reuse, via a thin
`AGENT=arkos` wrapper) - `scenarios.yaml` and `security_checks.py` stay
genuinely per-agent content. Comage/Advantage/Finage still have no
evaluation scenarios yet; they have no runtime workflow to evaluate
(`evaluations/{comage,advantage,finage}/README.md`).

`run_acceptance_gate.py` is the layered entrypoint
`make day1|d1 check agents` actually invokes for Tekos specifically (see
`ansible/roles/agents/tasks/check.yml`'s `run_acceptance_gate.yml`
include, which runs it as a one-shot in-cluster Job): it combines this
file's 20 scenarios (75% threshold) with `security_checks.py` and
`gate_checks.py` (both 100% mandatory) into one exit code and one
machine-readable JSON summary line. Run any of the three modules directly
for a narrower check, or the combined gate for what
`make day1|d1 check agents` runs:

```bash
cd evaluations/tekos
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://tekos.apps.<cluster-domain>
export TEKOS_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/tekos-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / SALES_DB_MCP_URL /
# AI_GATEWAY_URL default to their in-cluster Service DNS names - override if
# running this from outside the cluster via a port-forward instead. Reaching
# those in-cluster names at all requires running from a network location the
# ADR-0037/ADR-0052 NetworkPolicies actually allow - see
# ansible/roles/agents/tasks/run_acceptance_gate.yml for how
# `make day1|d1 check agents`'s own Job satisfies that (the
# "acceptance-gate" workload identity, narrowly allow-listed alongside
# the other real per-workload callers).
python3 run_acceptance_gate.py     # everything `make day1|d1 check agents` runs, one exit code
python3 run_scenarios.py           # just the 20 scenarios
```

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters); `run_scenarios.py` maps each `type` to one
handler function and prints a pass/fail table plus the overall rate against
the 75% threshold, exiting non-zero on failure so it's CI-friendly once a
live cluster is reachable from a GitHub Actions runner (not yet true for
this project - see `.github/README.md`). `gate_checks.py`'s one check
needs no live cluster and is wired into `.github/workflows/lint.yml`'s
`policy-as-code` job accordingly.

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9), tool-triggered
retrieval (10-11), MCP Gateway policy enforcement (12-13, 18), model
routing/classification fail-closed behavior (14-15, config-consistency
checks that don't need a live cluster), BFF JWT validation (16-17),
namespace isolation (19), and service health (20).

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what "make
check" and a full evaluation run require.

## Security-negative checks

`security_checks.py` (same setup as above, run from this directory) checks
identity-propagation, classification and entitlement behavior that isn't
part of the fixed 20-scenario acceptance count (these are negative/security
checks, not acceptance coverage): the BFF actually forwards the caller's
token to the Agent Runtime, the Runtime ignores a forged `user_sub` in the
request body rather than treating it as authoritative, Confluence is
correctly classified C2 with `external_model_policy.allow_context: false`
(a config-only check, no live cluster needed), `X-Zuno-Local-Only: true`
actually forces `components/ai-gateway` to pick the local provider even
for a C2 request that would otherwise be SaaS-eligible, the two-dimension
group model is enforced server-side in both directions: a caller with the
`agent_tekos` entitlement but no business role is denied `search_confluence`
by the MCP Gateway (403), and a caller with the `consultant` business role
but no `agent_tekos` entitlement is denied by the BFF itself (403) before
the request ever reaches the Agent Runtime, and a direct call to
`sales-db-mcp` that bypasses the MCP Gateway entirely (no
`X-Zuno-Gateway-Token`) is denied by the server itself (401) - the
workload-identity layer required in addition to the NetworkPolicy
boundary (`gitops/charts/mcp-sales-db`'s `NetworkPolicy`, which an
HTTP-level check like this can't directly exercise;
`platform/security/check_workload_hardening.py` statically verifies that
policy and the rest of the hardening baseline exist in every chart's
rendered manifests instead).
