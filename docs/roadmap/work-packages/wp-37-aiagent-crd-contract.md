# WP-37: AIAgent CRD reconciliation contract

- **State:** Not started
- **ADRs:** ADR-0327 (To be implemented -> Implemented)
- **Depends on:** WP-31 (merged); ideally WP-33 (two non-Tekos agents give a better common-field sample)
- **Blocks:** WP-38
- **Estimated files touched:** ~7

> Execute this brief as a standalone task from the repository root. This WP
> is contract-only: schema + validation harness. The operator/controller is
> WP-38.

## Goal

Define the `zuno.ai/v1alpha1 AIAgent` CRD contract — spec (deployment
bindings, references only), status conditions, and the reconciliation
ownership boundary — and validate it statically against Tekos plus Arkos
(and Comage if merged), so WP-38 can implement the operator against a
proven contract.

## ADR references

Primary: [docs/adr/0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md](../../adr/0327-define-the-aiagent-crd-reconciliation-contract-before-implementing-the-operator.md)
(read fully — the ownership model, CRD contract and "operator must NOT"
lists are the specification).

Acceptance criteria (verbatim):

> - The CRD schema is validated against at least Tekos plus Arkos or Comage before implementation is declared complete.
> - Creating an `AIAgent` CR through GitOps produces the expected per-agent frontend/BFF/configuration resources without modifying shared platform services.
> - Deleting/suspending an `AIAgent` has a defined, safe lifecycle that does not delete shared data or secrets unexpectedly.
> - Cross-namespace references and inline secret material are rejected.
> - `status.conditions` provides useful readiness/error state consumed by `make check`.
> - Existing plain-manifest agents can be migrated incrementally without a flag day.

(Bullets 2, 3 and 5 are only fully dischargeable by WP-38's controller; this
WP delivers the contract + static validation that make them testable, and
bullets 1, 4 and 6's design.)

Spec contents per the ADR: references/selectors for agent name/namespace
intent, OKF bundle/source reference, frontend/BFF deployment profile + image
references, entitlement/business-role group bindings, logical RAG
collections, logical MCP/tool bindings, model-policy/profile reference,
exposure/route settings, observability/evaluation profile. NO secrets,
prompts, document bodies, OAuth tokens or raw credentials (referenced via
Vault/External Secrets only). Status: `status.conditions` must expose at
least config validity, OKF readiness, frontend readiness, BFF readiness,
runtime-binding readiness.

## Preconditions (verify before starting)

- WP-31 merged (Arkos exists as second real agent).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `operator/aiagent-operator/` (existing scaffold — build on it, note
  its framework), the deployed shapes of Tekos + Arkos
  (`gitops/charts/tekos/`, `gitops/charts/arkos/`, their Keycloak/policy
  wiring) — the CRD fields must cover exactly what is genuinely common.

## Repo changes (step by step)

1. **CRD schema:** `operator/aiagent-operator/config/crd/` —
   `zuno.ai/v1alpha1 AIAgent` with the spec/status fields above, OpenAPI
   validation rejecting inline secret-like fields and cross-namespace
   references (schema-level where expressible; validation-harness rules for
   the rest).
2. **Example CRs:** `operator/aiagent-operator/config/samples/` — one
   `AIAgent` per existing real agent (tekos, arkos, comage if merged),
   derived field-by-field from their live chart values.
3. **Static validation harness:**
   `operator/aiagent-operator/validate_contract.py` — validates the sample
   CRs against the CRD schema, enforces the reject rules (inline secrets,
   cross-namespace), and cross-checks each sample against the agent's actual
   chart values (image refs, groups, knowledge/tool declarations) so drift
   fails. Wire into `.github/workflows/lint.yml` (blocking).
4. **Contract doc:** `operator/aiagent-operator/CONTRACT.md` — the
   ownership boundary (Git/Argo CD owns shared apps + the CRs; operator owns
   generated per-agent resources; the ADR's "must NOT" list verbatim), the
   condition types, and the incremental migration path (plain-manifest agent
   → CR-managed, one agent at a time, no flag day).

## What NOT to touch

- Decision text of any existing ADR; the ADR-0344 dirty set.
- No controller/reconciler code (WP-38).
- Agent charts themselves (the harness reads them; it must not rewrite them).

## Acceptance checks (run from repo root; all must pass)

- `python3 operator/aiagent-operator/validate_contract.py` (exit 0)
- Deliberately add an inline secret field to a scratch sample → harness
  fails; remove the scratch.
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up

None — contract validation is repo-provable. (Cluster behavior is WP-38's.)

## Status updates (then re-run check_docs.py)

- After merge: ADR-0327 →
  `Implemented - see \`operator/aiagent-operator/config/crd/\`, \`operator/aiagent-operator/CONTRACT.md\`.`;
  index row `Implemented`; tracker → `Done`; this file's State; MEMORY.md
  dated bullet.

## Out of scope / deferred

- The operator/controller implementation and ADR-0113's closure (WP-38).
