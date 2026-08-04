# Tekos Evaluation

The 20 acceptance scenarios (ADR-0027) and the 75% pass-threshold report
(ADR-0028) for Tekos - the only functional agent in v0. The other four
agents have no evaluation scenarios yet; they have no runtime workflow to
evaluate (`evaluations/{comage,advantage,finage,arkos}/README.md`).

```bash
cd evaluations/tekos
pip install -r requirements.txt
export KEYCLOAK_URL=https://sso.apps.<cluster-domain>
export FRONTEND_URL=https://tekos.apps.<cluster-domain>
export TEKOS_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret secret/zuno/keycloak/tekos-frontend)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / SALES_DB_MCP_URL
# default to their in-cluster Service DNS names - override if running this
# from outside the cluster via a port-forward instead.
python3 run_scenarios.py
```

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters); `run_scenarios.py` maps each `type` to one
handler function and prints a pass/fail table plus the overall rate against
the 75% threshold, exiting non-zero on failure so it's CI-friendly once
`.github/workflows/` exists (currently none do - see `.github/README.md`).

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9), tool-triggered
retrieval (10-11), MCP Gateway policy enforcement (12-13, 18), model
routing/classification fail-closed behavior (14-15, config-consistency
checks that don't need a live cluster), BFF JWT validation (16-17),
namespace isolation (19), and service health (20).

This cannot be executed in the sandbox this repo was built in (no live
OpenShift cluster) - see the top-level feasibility plan for what "make
check" and a full evaluation run require.
