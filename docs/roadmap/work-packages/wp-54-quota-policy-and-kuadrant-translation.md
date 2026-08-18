# WP-54: Quota policy and Kuadrant translation (promotes ADR-0511)

- **State:** Not started
- **ADRs:** ADR-0511
- **Depends on:** WP-44 Part A (matrix generator exists to grow the
  quota column)
- **Blocks:** WP-55
- **Estimated files touched:** ~8 (Part A) + ~10 (Part B)

> Execute this brief as a standalone task from the repository root.
> Tracked in [docs/roadmap/okf-roadmap.md](../okf-roadmap.md).
> Before authoring any Kuadrant CR, run `oc explain` on the live CRDs
> (`ratelimitpolicies.kuadrant.io`, `authpolicies.kuadrant.io`) — the
> installed Connectivity Link version's schema is the truth, not docs.

## Goal

Declare usage limits per user/group/project in
`policies/quotas/quota-policy.yaml` with named quota classes and the
project→user→group precedence, and generate enforcement from it:
Kuadrant (Limitador/Authorino) resources for request rates, AI Gateway
config for token budgets.

## ADR references

ADR-0511 clauses 1–5; ADR-0512 consumes the project dimension.

## Preconditions (verify before starting)

- WP-44 Part A merged. `make d0 check connectivity_link` reports the
  Kuadrant operand healthy.
- Read: `policies/tools/tool-policy.yaml` header (file-shape
  precedent); `gitops/charts/connectivity-link/`;
  `components/ai-gateway/app/` usage-tracking code (ADR-0029) and
  `maas_adapter.py`.
- Ask the user before any cluster-side validation step.

## Repo changes (step by step)

**Part A — policy file + schema + matrix:**
1. `policies/quotas/quota-policy.yaml`: documented header (enforcement
   formula, precedence order project → user → group in project context,
   user → group outside), quota classes (`standard`, `intensive` at
   minimum), per-dimension limits (requests-per-window; token budgets
   for inference), per-class fail-open/fail-closed posture (default
   closed), ADR-0512's binding validity window.
2. Schema/validator: optional `zuno.quota_class` on task frontmatter;
   quota-policy lint (classes referenced exist, windows parse) in the
   policy-as-code job; matrix generator renders the real quota column;
   regenerate all matrices.

**Part B — enforcement generation:**
3. `platform/okf/generate_quota_enforcement.py`: quota-policy.yaml →
   (a) Kuadrant `RateLimitPolicy`/`AuthPolicy` manifests under
   `gitops/charts/` (a new small chart or the agent charts' templates —
   decide from `oc explain` + chart layout at execution, record the
   choice in the State log); (b) AI Gateway token-budget config. Both
   with `--check` drift mode, wired into lint.
4. AI Gateway: budget check against the generated config at request
   accounting time (it already meters tokens per ADR-0029); explicit
   quota-exceeded error shape; metrics per dimension.
5. Data-plane placement decision (ADR-0511 clause 4): gateway listener
   vs BFF-side Limitador consult — decide at execution from cluster
   state, record in the State log and the chart README.

## What NOT to touch

Standard list; plus: the ADR-0036 intersection path (quota never
bypasses or relaxes it); no hand-authored Kuadrant CRs outside the
generator's output.

## Acceptance checks (run from repo root; all must pass)

- Policy lint + both `--check` modes green; hand-editing a limit
  without regenerating fails lint (restore after proving).
- AI Gateway suite covers budget exhaustion (explicit error, metric
  emitted) and the precedence order with and without a project binding.
- `helm lint` clean on touched charts; `check_docs.py` passes.

## Operator / human follow-up (not executable by the model)

Apply/sync the generated chart; demo: one user exceeds a request limit
(explicit quota error), token-budget exhaustion visible in metrics;
confirm counters keyed correctly per dimension in Limitador.

## Status updates (then re-run check_docs.py)

On merge: ADR-0511 → `Partially implemented (policy + generation +
gateway budget merged; live Kuadrant verification pending)`; after the
demo → `Implemented - see policies/quotas/ and
platform/okf/generate_quota_enforcement.py.` Index + tracker +
MEMORY.md accordingly.

## Out of scope / deferred

- Project binding verification (WP-55). Per-model cost-weighted budgets
  (future ADR if wanted). Webhook/burst tuning.
