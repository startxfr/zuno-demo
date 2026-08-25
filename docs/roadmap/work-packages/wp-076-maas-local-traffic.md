# WP-076: Route ai-gateway's local model traffic through MaaS

- **State:** Not started
- **ADRs:** ADR-0521 (Proposed)
- **Depends on:** WP-27 (Done — the live MaaS proof this generalizes)
- **Estimated files touched:** ~10-15 (scales with the number of local models)

> Execute this brief as a standalone task from the repository root. Like
> WP-27, this is cluster-dependent: the repo work is manifests, config and
> tests; the API-key issuance discovery, the latency comparison and the
> live fallback test all need the live MaaS environment to discharge.

## Goal

Generalize WP-27's proven `gpt-oss-20b` MaaS governance pattern to every
local model, and switch `ai-gateway`'s local-model transport from a direct
Service call to MaaS, per ADR-0521.

## ADR references

Primary: [docs/adr/0521-route-local-model-traffic-through-maas.md](../../adr/0521-route-local-model-traffic-through-maas.md)
(read its full Decision list — items 1-9 map directly to the repo changes
below).

Acceptance criteria: every local model has a `MaaSModelRef`/`MaaSSubscription`/
`MaaSAuthPolicy` triple proven by the same positive/negative-group test WP-27
established; `maasAdapter.enabled: true` with every local provider entry
`via_maas: true`, pointed at the internal gateway Service; a documented live
latency comparison; a live-tested fallback (MaaS unreachable → direct call
still succeeds); `X-Zuno-Request-Id` confirmed in MaaS/Kuadrant/vLLM's own
logs; an explicit recorded decision on `quota.py`'s `TokenBudgetLedger`.

Named resources: `MaaSModelRef`, `MaaSSubscription`, `MaaSAuthPolicy`,
`maas-default-gateway`, `TokenRateLimitPolicy`; builds directly on WP-27's
`gitops/charts/models/templates/maas.yaml` /
`networkpolicy-gptoss.yaml` / `llminferenceservice-gptoss.yaml` patterns.

## Preconditions (verify before starting)

- WP-27 Done, ADR-0201 Implemented (already true as of 2026-08-25).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/ai-gateway/app/maas_adapter.py` (transport, already
  built), `platform/ai-gateway/provider-routing.yaml` (the `via_maas`/
  `maas_model_ref` schema comment and current provider list),
  `components/ai-gateway/app/main.py`'s `_invoke_with_fallback` (the
  existing fallback chain this reuses), `components/ai-gateway/app/quota.py`
  (the token-budget ledger item 9 evaluates),
  `docs/roadmap/evidence/adr-0114-maas-coverage.md` (the comparison this WP
  concludes).

## Repo changes (step by step)

1. **API-key discovery (operator step, not executable by the model):**
   determine how MaaS actually issues an `sk-oai-...` API key on the live
   cluster (no issuance flow is documented anywhere in this repo — only
   `/internal/v1/api-keys/validate` has been observed). Record the finding
   in this WP or a new evidence doc under `docs/roadmap/evidence/`.
2. **Vault seed:** once a real key exists, seed it at `maas/gateway-api-key`
   (the path `ansible/roles/vault/tasks/install.yml` and
   `gitops/charts/ai-gateway/templates/externalsecret-maas.yaml` already
   expect — no manifest change needed, just the operator seeding step).
3. **Enable the adapter and per-model config:** `maasAdapter.enabled: true`
   in `gitops/charts/ai-gateway/values.yaml`; for each local provider entry
   in `platform/ai-gateway/provider-routing.yaml`, add a `via_maas: true`
   sibling entry (keep the existing direct entry too, for item 5's fallback)
   with `maas_model_ref` set to that model's `<namespace>/<MaaSModelRef
   name>` identity, endpoint pointed at
   `maas-default-gateway-istio.openshift-ingress.svc` (internal, not the
   external route).
4. **Generalize the governance manifests:** for every local model beyond
   `gpt-oss-20b`, extend `gitops/charts/models/templates/maas.yaml`'s
   `MaaSModelRef`/`MaaSSubscription` range, add the equivalent
   NetworkPolicy allowance (`gateway.networking.k8s.io/gateway-name:
   maas-default-gateway` from `openshift-ingress`) to that model's own
   NetworkPolicy template, and add the repeated `--served-model-name` args
   (KServe's two names plus the MaaS identity) to that model's
   `LLMInferenceService` template.
5. **Verify the fallback chain live:** confirm `_invoke_with_fallback`
   already produces the desired "MaaS unreachable → direct candidate"
   behavior with no code change — test by making MaaS temporarily
   unreachable (e.g. a scoped NetworkPolicy deny) and confirming a request
   still succeeds via the kept direct-Service candidate.
6. **Live latency comparison:** measure and document request latency
   MaaS-routed vs. direct, for at least one model, before considering that
   model's cutover complete.
7. **Trace correlation verification:** confirm `X-Zuno-Request-Id` appears in
   MaaS/Kuadrant/vLLM's own logs for a real request routed through MaaS, not
   only inside `maas_adapter.py`.
8. **`quota.py` equivalence evaluation:** compare `TokenBudgetLedger`'s
   window/precedence semantics (ADR-0511 clause 2) against MaaS's generated
   `TokenRateLimitPolicy` for a MaaS-routed model; record the decision
   (kept / scoped to non-MaaS providers only / removed) in ADR-0521's status
   or a dated note — do not remove `quota.py` code speculatively before this
   comparison is done.

## What NOT to touch

- WP-27's proven `gpt-oss-20b` NetworkPolicy/vLLM-alias fix — extend the
  pattern to other models, don't restructure what already works.
- `quota.py` itself, until step 8's equivalence check is recorded — no
  speculative removal.
- External-provider (`openai`/`gemini`/`anthropic`/`mistral`) entries in
  `provider-routing.yaml` — this WP is local-model traffic only; external
  egress through MaaS stays governed by WP-27's existing
  `MAAS_EXTERNAL_EGRESS_ENABLED` gate and lifecycle decision.

## Acceptance checks (run from repo root; all must pass)

- `helm lint` + `helm template` on `gitops/charts/models` and
  `gitops/charts/ai-gateway` (all new/changed resources render)
- `python3 -m pytest components/ai-gateway/ -q`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: discover and exercise the real MaaS API-key issuance flow (step
   1) — needs whatever access level actually mints a key, not yet identified
   from this repo alone.
2. Operator: run the live latency comparison and the live fallback test
   (steps 5-6) against the real cluster.
3. Operator + user: review the `quota.py` equivalence finding (step 8) and
   confirm the retire/keep decision before any code deletion.

## Status updates (then re-run check_docs.py)

- After repo merge (manifests/config for at least one additional model,
  fallback verified in code review): ADR-0521 → `Partially implemented`;
  index row to match; tracker → `Operator pending`.
- After the operator live steps land (API key minted, latency documented,
  fallback proven, trace correlation confirmed, `quota.py` decision
  recorded): ADR-0521 → `Implemented`; index row `Implemented`; tracker →
  `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Removing `quota.py` outright — a future WP once step 8's equivalence
  check is recorded and approved.
- External-model (SaaS) traffic through MaaS — separate lifecycle decision,
  already gated by WP-27's `MAAS_EXTERNAL_EGRESS_ENABLED`.
