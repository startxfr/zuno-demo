# Tekos Evaluation

The 20 acceptance scenarios (ADR-0027) and the 75% pass-threshold report
(ADR-0028) for Tekos - the only functional agent in v0. The other four
agents have no evaluation scenarios yet; they have no runtime workflow to
evaluate (`evaluations/{comage,advantage,finage,arkos}/README.md`).

`run_acceptance_gate.py` (ADR-0053) is the layered entrypoint `make check`
actually invokes (see `ansible/roles/agents/tasks/check.yml`'s
`run_acceptance_gate.yml` include, which runs it as a one-shot in-cluster
Job): it combines this file's 20 scenarios (75% threshold) with
`security_checks.py` and `gate_checks.py` (both 100% mandatory) into one
exit code and one machine-readable JSON summary line. Run any of the three
modules directly for a narrower check, or the combined gate for what
`make check` runs:

```bash
cd evaluations/tekos
pip install -r requirements.txt
export KEYCLOAK_URL=https://sso.apps.<cluster-domain>
export FRONTEND_URL=https://tekos.apps.<cluster-domain>
export TEKOS_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret secret/zuno/keycloak/tekos-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password secret/zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / SALES_DB_MCP_URL /
# AI_GATEWAY_URL default to their in-cluster Service DNS names - override if
# running this from outside the cluster via a port-forward instead. Reaching
# those in-cluster names at all requires running from a network location the
# ADR-0037/ADR-0052 NetworkPolicies actually allow - see
# ansible/roles/agents/tasks/run_acceptance_gate.yml for how `make check`'s
# own Job satisfies that (the "acceptance-gate" workload identity, narrowly
# allow-listed alongside the other real per-workload callers).
python3 run_acceptance_gate.py     # everything make check runs, one exit code
python3 run_scenarios.py           # just the 20 scenarios
```

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters); `run_scenarios.py` maps each `type` to one
handler function and prints a pass/fail table plus the overall rate against
the 75% threshold, exiting non-zero on failure so it's CI-friendly once a
live cluster is reachable from a GitHub Actions runner (not yet true for
this project - see `.github/README.md`). `gate_checks.py`'s one check needs
no live cluster (same as `model_router_fails_closed`/
`model_router_prefers_local` above) and is wired into
`.github/workflows/lint.yml`'s `policy-as-code` job for exactly that
reason.

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9), tool-triggered
retrieval (10-11), MCP Gateway policy enforcement (12-13, 18), model
routing/classification fail-closed behavior (14-15, config-consistency
checks that don't need a live cluster), BFF JWT validation (16-17),
namespace isolation (19), and service health (20).

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what "make
check" and a full evaluation run require.

## Security-negative checks (ADR-0032, ADR-0033, ADR-0034, ADR-0035, ADR-0037, ADR-0040)

`security_checks.py` (same setup as above, run from this directory) checks
identity-propagation, classification and entitlement behavior that isn't
part of the fixed 20-scenario acceptance count (ADR-0027 fixes that count;
these are negative/security checks for specific ADRs, not acceptance
coverage): the BFF actually forwards the caller's token to the Agent
Runtime, the Runtime ignores a forged `user_sub` in the request body rather
than treating it as authoritative, Confluence is correctly classified C2
with `external_model_policy.allow_context: false` (a config-only check, no
live cluster needed), `X-Zuno-Local-Only: true` actually forces
`components/ai-gateway` to pick the local provider even for a C2 request
that would otherwise be SaaS-eligible, ADR-0040's two-dimension group
model is enforced server-side in both directions: a caller with the
`agent_tekos` entitlement but no business role is denied `search_confluence`
by the MCP Gateway (403), and a caller with the `consultant` business role
but no `agent_tekos` entitlement is denied by the BFF itself (403) before
the request ever reaches the Agent Runtime, and a direct call to
`sales-db-mcp` that bypasses the MCP Gateway entirely (no
`X-Zuno-Gateway-Token`) is denied by the server itself (401) - the
workload-identity layer ADR-0037 requires in addition to the NetworkPolicy
boundary (`gitops/charts/mcp-sales-db`'s `NetworkPolicy`, which an
HTTP-level check like this can't directly exercise;
`platform/security/check_workload_hardening.py` statically verifies that
policy and the rest of the ADR-0052 hardening baseline exist in every
chart's rendered manifests instead).
