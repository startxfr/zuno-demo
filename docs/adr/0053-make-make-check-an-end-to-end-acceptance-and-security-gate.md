# ADR-0053: Make make check an end-to-end acceptance and security gate

- **Status:** Implemented
- **Target:** v0
- **Date:** 2026-08-05
- **Decision owners:** Zuno Demo architecture team

## Context

The current check path is primarily service-health oriented. The project requires proof that the agent chain, classification, authentication, RAG, MCP and model routing behave correctly, not merely that pods answer `/healthz`.

## Decision

`make check` must run layered checks: infrastructure readiness, Keycloak login/claims, BFF and Runtime auth, RAG retrieval, MCP allow/deny, local model inference, permitted SaaS fallback, classification enforcement, SSE first token, citations, and the 20 Tekos evaluation scenarios. Security-negative cases are first-class acceptance tests.

## Alternatives considered

- Keep the current implementation unchanged and rely on conventions or documentation. Rejected because the reviewed code shows that implicit contracts already diverge from intended behavior.
- Defer the decision until all five agents are implemented. Rejected because this decision affects the platform contract and should be resolved before additional agents amplify the current pattern.

## Consequences

The demo gains one operator command that proves business behavior and critical security assumptions. Checks may take longer but failures become actionable.

## Security considerations

Mandatory negative tests include unauthorized agent access, wrong group, forged user identity, direct MCP bypass, C2 Confluence to SaaS denial and missing/expired tokens.

## Operational considerations

Return machine-readable results and non-zero exit status when mandatory gates fail. Preserve the 75% quality threshold while making security checks 100% mandatory.

## Implementation state

**Implemented (2026-08-05)**: `make check` now runs the full layered gate
this ADR's Decision names, as one Ansible role (`ansible/roles/agents/
tasks/check.yml` → `run_acceptance_gate.yml`) driving one Python
orchestrator (`evaluations/tekos/run_acceptance_gate.py`).

**Layering, mapped to the Decision's list**: infrastructure readiness
(existing OKF structural validation + frontend `/healthz`, `check.yml`'s
pre-existing Layer 0, kept as-is) → Keycloak login/claims, BFF/Runtime
auth, RAG retrieval, MCP allow/deny, local model inference, classification
enforcement, SSE first token and citations (`evaluations/tekos/
scenarios.yaml`'s 20 fixed scenarios, ADR-0027/0028 - scenario 3 was
extended in this pass to decode and assert the token's `groups` claim, not
just that login succeeds, since "Keycloak login/claims" names both) →
permitted SaaS fallback (`evaluations/tekos/gate_checks.py`, new - the one
capability this ADR names that no existing scenario or security check
covered; a config-consistency check against `platform/ai-gateway/
provider-routing.yaml`, the same no-live-cluster-needed style as the
already-existing `model_router_fails_closed`/`model_router_prefers_local`
scenarios, and for the same reason: proving a live SaaS *fallback* would
require deliberately breaking the local model's availability, which a
`make check` gate has no safe way to do).

**"Security-negative cases are first-class acceptance tests" /
"Mandatory negative tests include unauthorized agent access, wrong group,
forged user identity, direct MCP bypass, C2 Confluence to SaaS denial and
missing/expired tokens"**: `evaluations/tekos/security_checks.py` already
covered five of these six from earlier phases (business-role-without-
entitlement and entitlement-without-business-role for "unauthorized agent
access"/"wrong group", forged `user_sub` for "forged user identity", the
sales-db-mcp bypass for "direct MCP bypass", `X-Zuno-Local-Only` forcing
local for "C2 Confluence to SaaS denial") and `bff_rejects_missing_jwt`
already covered "missing" tokens; the "expired" half of the sixth was a
genuine gap - no code in this repository could construct a validly-signed
expired token without either a real Keycloak instance or forging its
private key. Closed with new, fully offline tests
(`components/agent-runtime/tests/test_auth.py` and
`components/mcp-gateway/tests/test_auth.py`, structurally identical since
`app/auth.py` itself is a deliberate per-service duplicate): each mints
its own RSA keypair, monkeypatches the module's JWKS client to vouch for
it, and proves by execution (not just by reading the code) that an
expired-but-correctly-signed token, and a well-formed token signed by an
untrusted key, are both rejected with 401 - PyJWT's own default `exp`/
signature verification, which auth.py never disables. Both test files
were run directly in this environment (no live cluster needed) and pass,
and are now wired into `.github/workflows/lint.yml`'s `python` job.

A real, adjacent bug surfaced and fixed while implementing the mandatory
"direct MCP bypass" case under this ADR's new execution model: previously
that check only accepted a clean HTTP 401 as "denied"; once `make check`
started running it from inside the cluster (see below), a NetworkPolicy-
level deny (a connection timeout, since ADR-0037/0052's NetworkPolicies
never allow-list this test identity to `sales-db-mcp`, deliberately)
would have raised an unhandled exception and been misreported as the
check *erroring*, not *passing* - fixed to treat either denial layer as a
valid pass, which is in fact the stronger, now-actually-exercised
guarantee.

**"Return machine-readable results and non-zero exit status when mandatory
gates fail. Preserve the 75% quality threshold while making security
checks 100% mandatory"**: `run_acceptance_gate.py` combines all three
layers (20 scenarios at 75%, `security_checks.py` and `gate_checks.py`
both at 100%) into one process, prints the same human-readable tables each
module already printed standalone, and always ends with one line of JSON
(`{"scenarios": {...}, "security_checks": {...}, "gate_checks": {...},
"overall": "PASS"|"FAIL"}`) - machine-readable without inventing a second
output mode. Exit code is non-zero unless all three gates pass.

**Execution model, and why it needed more than "add a script"**: most of
what this gate must call (`agent-runtime`, `mcp-gateway`, `ai-gateway`,
`rag-service`) has no OpenShift Route - reachable only over in-cluster
Service DNS, by design (ADR-0023). `run_acceptance_gate.yml` (new) runs
the gate as a one-shot Job in `zuno-ai` (same "Job, not a GitOps
Application" reasoning as `ansible/roles/sql_schema`), reading the
Vault-issued demo-persona password and `tekos-frontend` client secret
already synced to `zuno-auth` by the `keycloak` role and copying them into
a Job-local Secret, with the scripts themselves delivered via a ConfigMap
(`python:3.12-slim` + `pip install` at run time, matching `sql_schema`'s
precedent of an off-the-shelf image over a purpose-built one for a
one-shot batch Job - no new image, no CI matrix change needed).

This surfaced a real, structural consequence of ADR-0037/ADR-0052's own
precise, per-workload NetworkPolicies that a from-outside design would
have missed: an arbitrary test pod cannot reach most of these services at
all, by design. Rather than weaken any existing policy, the Job runs as a
new, real, narrowly-scoped `acceptance-gate` workload identity
(`app.kubernetes.io/name: acceptance-gate` in `zuno-ai`), explicitly
allow-listed - the same deliberate, additive way every other legitimate
caller in this repository already is - in `gitops/charts/{agent-runtime,
mcp-gateway,ai-gateway}/templates/networkpolicy.yaml` and a new
`gitops/charts/tekos/templates/networkpolicy.yaml` (the BFF had no
dedicated NetworkPolicy of its own before this ADR, relying only on its
namespace's same-namespace-plus-router default-deny baseline).
`rag-service` needed no change: `zuno-data`'s existing namespace-wide
platform baseline already admits any `zuno-ai` pod. `sales-db-mcp`
deliberately received no such allowance - see the bypass-check fix above.

**A real, separate, pre-existing bug surfaced but deliberately not fixed
here**: wiring `KEYCLOAK_URL` for the Job required picking a real
hostname, which exposed that `gitops/charts/keycloak/templates/
keycloak.yaml`'s actual Keycloak custom resource is configured with
hostname `keycloak.<domain>`, while `gitops/charts/tekos/templates/
_helpers.tpl`'s `keycloakIssuerUrl` and every `evaluations/tekos/*.py`
script's `KEYCLOAK_URL` *default* instead assume a `sso.<domain>`
convention that no Route in this repository actually creates. The Job
uses the real hostname (`keycloak.<domain>`), so this ADR's own gate is
unaffected, but the mismatch is real and would break the live Tekos
frontend's OIDC login on an actual cluster. It belongs to ADR-0032/0033's
already-"Implemented" identity plumbing (three charts' checked-in
`keycloakIssuer` values, none of which any role currently wires
dynamically from the discovered `cluster_base_domain` either), not to this
ADR's own scope - flagged here rather than silently patched as a drive-by
change to other ADRs' already-closed implementation state.

**Not executed**: the Job itself has not run in a real cluster (no live
OpenShift/Keycloak/Vault exists in this environment, the same constraint
as every other cluster-dependent role in this repository) - `ansible-
playbook --syntax-check` passed for every playbook, `helm lint` passed for
every touched chart, and `gate_checks.py` plus both new `test_auth.py`
files were actually executed here and pass for real.

## Acceptance criteria

- The implementation is merged through the normal repository review process.
- Relevant documentation and `MEMORY.md` are updated to describe the implemented state rather than the target state.
- `make check` or component-specific automated tests demonstrate the behavior described in this ADR.
- Security-negative tests are included whenever the decision changes an authorization, identity, data-classification or trust boundary.

## Related ADRs

- ADR-0027
- ADR-0028
- ADR-0030
- ADR-0032
- ADR-0035
- ADR-0036
- ADR-0045

## Review evidence

This decision is grounded in the repository snapshot reviewed on 2026-08-05 (`zuno-demo-main.zip`) and the project requirements already recorded in the repository. Paths named in the Context section identify the primary implementation evidence where applicable.
