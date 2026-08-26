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
`make day2|d2 check agents` actually invokes for Tekos specifically (see
`ansible/roles/agents/tasks/check.yml`'s `run_acceptance_gate.yml`
include, which runs it as a one-shot in-cluster Job): it combines this
file's 20 scenarios (75% threshold) with `security_checks.py` and
`gate_checks.py` (both 100% mandatory) into one exit code and one
machine-readable JSON summary line. Run any of the three modules directly
for a narrower check, or the combined gate for what
`make day2|d2 check agents` runs:

```bash
cd evaluations/tekos
pip install -r requirements.txt
export KEYCLOAK_URL=https://keycloak.apps.<cluster-domain>
export FRONTEND_URL=https://tekos.apps.<cluster-domain>
export TEKOS_FRONTEND_CLIENT_SECRET=$(vault kv get -field=client_secret zuno/keycloak/tekos-frontend)
export DEMO_PERSONA_PASSWORD=$(vault kv get -field=password zuno/keycloak/demo-personas)
# BFF_URL / RUNTIME_URL / MCP_GATEWAY_URL / RAG_SERVICE_URL / CONFLUENCE_MCP_URL /
# AI_GATEWAY_URL default to their in-cluster Service DNS names - override if
# running this from outside the cluster via a port-forward instead. Reaching
# those in-cluster names at all requires running from a network location the
# ADR-0037/ADR-0052 NetworkPolicies actually allow - see
# ansible/roles/agents/tasks/run_acceptance_gate.yml for how
# `make day2|d2 check agents`'s own Job satisfies that (the
# "acceptance-gate" workload identity, narrowly allow-listed alongside
# the other real per-workload callers).
python3 run_acceptance_gate.py     # everything `make day2|d2 check agents` runs, one exit code
python3 run_scenarios.py           # just the 20 scenarios
```

Scenarios are defined in `scenarios.yaml` (id, title, `type`, and
type-specific parameters); `run_scenarios.py` maps each `type` to one
handler function and prints a pass/fail table plus the overall rate against
the 75% threshold, exiting non-zero on failure so it's CI-friendly once a
live cluster is reachable from a GitHub Actions runner (not yet true for
this project - see `.github/README.md`). `gate_checks.py`'s checks need no
live cluster and are wired into `.github/workflows/lint.yml`'s
`policy-as-code` job accordingly (see below for what they check).

Coverage: portal/tile access gating (scenarios 1, 2, 4-6), authentication
(3), the chat contract synchronous and streaming (7-9), tool-triggered
retrieval (10-11), MCP Gateway policy enforcement (12-13, 18), model
routing/classification fail-closed behavior (14-15, config-consistency
checks that don't need a live cluster), BFF JWT validation (16-17),
namespace isolation (19), and service health (20).

`gate_checks.py` holds three config-only checks (no live cluster needed):
permitted SaaS fallback at C2, `write-code`'s model-routing preference
genuinely resolving to `mistral-codestral` first (ADR-0417), and Tekos's
OKF bundle staying free of the DAT-drafting/image-generation capabilities
that belong to Arkos alone (ADR-0415) - all three are wired into
`.github/workflows/lint.yml`'s `policy-as-code` job.

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
`confluence-mcp` that bypasses the MCP Gateway entirely (no
`X-Zuno-Gateway-Token`) is denied by the server itself (401) - the
workload-identity layer required in addition to the NetworkPolicy
boundary (`gitops/charts/mcp-confluence`'s `NetworkPolicy`, which an
HTTP-level check like this can't directly exercise;
`platform/security/check_workload_hardening.py` statically verifies that
policy and the rest of the hardening baseline exist in every chart's
rendered manifests instead); and, closing a gap a stress-testing pass over
Tekos surfaced (ADR-0415/ADR-0036), a direct `generate_image` call "as
Tekos" is denied (403) by the MCP Gateway's agent_declaration factor alone
- `generate_image`'s `allowed_groups` includes `consultant`, so this
isolates the boundary from group/role noise - and a live chat turn that
explicitly asks Tekos for a generated image still returns an empty
`images` list, since Tekos's task never declares that capability in the
first place (Arkos/Advantage/Comage's alone).

## Exploratory stress test

`stress_test.py` (same setup as above, run from this directory) is a
broad, deliberately-uncapped battery of prompts run live as `consultant-01`
against Tekos's real chat surface, covering: technical Q&A across every
declared RAG domain (OpenShift/Kubernetes/Keycloak/Ansible/ArgoCD/Helm/Go),
Confluence-live-read-triggering prompts, code-generation prompts across
several `write-code` trigger-pattern branches, a DAT-drafting boundary
probe and an image-generation boundary probe (Tekos has neither capability
- see `gate_checks.py`'s/`security_checks.py`'s deterministic counterparts
of this same boundary above), a handful of adversarial/edge prompts (a
dual live-read+code trigger, a very short and a very long message, a
mid-conversation pivot to an out-of-scope request reusing `run_id`), and
two ai-gateway-direct model-routing correlation checks
(`answer-technical-question` should prefer `local-gpt-oss`, `write-code`
should prefer `mistral-codestral`, per `agents/tekos/agent.okf.md`'s
generated "Model routing" table). **Not part of `run_acceptance_gate.py`/
ADR-0053's mandatory gate** - unlike `security_checks.py`/`gate_checks.py`,
several of its assertions (false-capability-claim phrase heuristics, "did
the preferred model actually answer vs. legitimately fall back") are
exploratory/informational by design, not hard release gates. Run with
`python3 stress_test.py`.
