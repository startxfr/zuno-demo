# WP-54: Quota policy and Kuadrant translation (promotes ADR-0511)

> ADR-0511 retargeted to v0.5 (make the MaaS governance plane live and used by agents) on 2026-08-24 — see `docs/roadmap/versions.md`.

- **State:** Operator pending (Parts A+B merged 2026-08-18; demo
  Gateway/HTTPRoute/AuthPolicy attached and `quotaEnforcement.enabled`
  flipped `true` the same day, discovering and fixing six further live
  bugs — see the connectivity-link chart README. 2026-08-21: with all six
  fixed and RateLimitPolicy/AuthPolicy both `Enforced: True`, the 429 demo
  still 500s on every request. Root-caused to a genuine Kuadrant wasm-shim
  defect (not Authorino, not our config) — see ADR-0511's 2026-08-21
  implementation note for the full trace. A direct gRPC call to Authorino,
  bypassing the wasm-shim, proves Authorino cleanly ALLOWs a fresh token
  and cleanly DENYs an expired one; the same fresh token through the real
  gateway still 500s. Not fixable from this repo — flagging for upstream
  Red Hat Connectivity Link, staying `Operator pending`.)
  **2026-08-24: retracted — see WP-071.** The wasm-shim binary was never
  the fault. Live diagnosis found Envoy's `kuadrant-auth-service` cluster
  trusts OpenShift's `service-ca.crt`, while Authorino's cert was issued
  by `vault-issuer-istio` — a locally-fixable TLS trust mismatch, not an
  upstream defect. A second gap was specific to this gateway: Kuadrant's
  own generated `EnvoyFilter` never adds TLS to the ext_authz cluster for
  any gateway; `maas-default-gateway` only worked via a separate
  RHOAI-owned filter this gateway never had. WP-071 fixed both (Authorino
  Service CA cert + a new mirroring `EnvoyFilter`) and verified live:
  repeated `401` responses through `zuno-agent-gateway`, zero
  `CERTIFICATE_VERIFY_FAILED`, `cx_connect_fail` delta `0`, Authorino's own
  log shows the request arriving. The request-limit half of this demo is
  no longer blocked — only the final 429-exceedance acceptance run (real
  token, repeated requests) remains, a normal remaining task.
  **Placement decision (Part B step 5):** Kuadrant-native —
  the generated per-class `RateLimitPolicy`s live in the
  connectivity-link chart (it owns the Kuadrant plane), values-gated
  off (`quotaEnforcement.enabled: false`) because agent chat enters
  via OpenShift Routes today and RLPs need a Gateway API targetRef;
  the live cluster shows the supported flow (policy CR → Kuadrant
  operator → compiled Limitador descriptors — the MaaS token limits
  already ride it, and the Limitador CR is operator-owned, never
  co-edited). BFF-direct Limitador consult rejected (would move policy
  into per-agent Go code). Token budgets: `app/quota.py` in ai-gateway
  (in-process fixed-window ledger — single-replica demo scope; the
  durable counter plane stays Limitador), checked pre-dispatch (429
  with class/dimension/budget/window), consumed where usage is
  metered. **Recorded gaps:** streaming responses carry no
  usage_metadata (pre-existing — record_usage never ran there either),
  so only non-streaming consumption is metered; the group counter keys
  the full sorted group-set, not per-group; the
  X-Zuno-Quota-Class/X-Zuno-Project-Id headers are accepted but no
  caller sends them yet (agent-runtime wiring lands with WP-55/WP-061;
  WP-47, originally named here, was abandoned and replaced by WP-061).
  ai-gateway suite: 84 passed (python3.12 venv — NOTE: redis==8.1.0
  needs ≥3.10, system 3.9 venv fails at install). helm lint clean;
  enabled render = 2 RLPs, disabled = none.
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
**Unblocked 2026-08-24 (WP-071)** — the 2026-08-21 wasm-shim diagnosis is
retracted; the real cause (an Authorino/Envoy TLS trust mismatch plus a
gateway-specific missing-TLS gap) is fixed and live-verified. Remaining:
run the actual 429-exceedance pass with a real token — a normal
acceptance step, not blocked by any external defect.

## Status updates (then re-run check_docs.py)

On merge: ADR-0511 → `Partially implemented (policy + generation +
gateway budget merged; live Kuadrant verification pending)`; after the
demo → `Implemented - see policies/quotas/ and
platform/okf/generate_quota_enforcement.py.` Index + tracker +
MEMORY.md accordingly.

## Out of scope / deferred

- Project binding verification (WP-55). Per-model cost-weighted budgets
  (future ADR if wanted). Webhook/burst tuning.
