# WP-120: Guardrail policy as NeMo rails configuration

- **State:** Repo work merged (2026-09-02) — live discovery still pending: the chart, the client
  backend and the tests are in; the `NemoGuardrails` CR has never been deployed, so the
  operand's request/response contract is unverified
- **ADRs:** [ADR-0540](../../adr/0540-express-guardrail-policy-as-nemo-rails-configuration.md)
- **Depends on:** WP-108 (the `GuardrailsOrchestrator` this sits beside and falls back to),
  WP-113 (the `zuno-trustyai` dashboard whose detections panel this changes)
- **Related:** [ADR-0534](../../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)

## Goal

Move the guardrail policy out of the agent-runtime image. `DETECTOR_PARAMS` — three PII classes
and five prompt-injection regexes — was a Python dict literal, so tuning a pattern meant editing
code, rebuilding an image and redeploying a request-path service. It now lives in
`custom_data.zuno_patterns` in a Helm-rendered ConfigMap that a `NemoGuardrails` server mounts,
and tuning is a YAML edit ArgoCD syncs.

Functional coverage is unchanged by construction: the same eight detection classes, still
observe-only, still non-blocking, still emitting `zuno.guardrails_evaluations` and
`zuno.guardrails_detections`.

## What landed

- `gitops/charts/trustyai-config/files/nemo-rails/observe/{config.yaml,rails.co,actions.py}` —
  the policy as data, the two recording flows, and a generic pattern-matching action that
  contains no policy of its own.
- `gitops/charts/trustyai-config/templates/{configmap-nemo-rails.yaml,nemoguardrails.yaml}`,
  gated behind `nemoGuardrails.enabled` (default `false`) as well as `trustyaiConfig.enabled`,
  so the `-d0` Application still renders nothing.
- `components/agent-runtime/app/clients/guardrails_client.py` — `GUARDRAILS_BACKEND`
  (`builtin` | `nemo`), `_evaluate_nemo()`, and `_detection_names()`. The reporting tail was
  extracted into a shared `_report()` so a backend switch cannot change the log shape or the
  metric semantics.
- 9 new tests in `components/agent-runtime/tests/test_guardrails.py` (18 total, all passing),
  including `PolicyParityWithRails`, which fails if the in-image copy and the rails policy drift.
- `policies/guardrails/README.md` rewritten from a two-line stub into the specification.
- `ansible/roles/trustyai_config/tasks/precheck.yml` reports the CR's conditions, its three CA
  booleans and the `bbrPlugin` flag, plus the ConfigMap's key set.

## The live discovery gate — 2 of 5 answered, at the cost of an incident

ADR-0540's design answers the cost question by construction (no `models:` block, so no
inference), but five things about the operand cannot be read from the CRD. The CR was deployed
on 2026-09-02 to establish them; the node it landed on crossed its eviction threshold before the
remaining three could be exercised, and the CR was backed out (`4f0d869d`). Two answers survive
and are recorded here so nobody redeploys to relearn them.

**Answered.**

1. **The Service is `zuno-guardrails` on port 80** — NOT the `<cr-name>-service` on 8000 that
   `detectorUrl` uses and that this WP originally assumed. `guardrails.nemoUrl` was wrong for
   exactly that reason and is corrected. The operator also creates a Route.
4. **Yes, a config with no `models:` block validates and starts.** The CR reached
   `DeploymentReady=True`, `RouteReady=True`, `ReconcileComplete=True`, with `status.ca` showing
   `odhTrustedCAFound: true` and `openshiftServingCAFound: true`. **This was the expensive
   question** — ADR-0540 Decision 2's cost gate. Had it required a model, every observed exchange
   would have become a GPU-backed inference call on a cluster whose quota is saturated, which was
   an escalation to the user rather than an implementation detail. It does not. The pattern-only
   rails design stands.

**Still open** — all three need the server actually answering, so they need a redeployment:

2. whether `GET /v1/rails/configs` lists `zuno-observe`;
3. whether `POST /v1/chat/completions` with `options.rails: ["input"]` and
   `log.activated_rails: true` returns the activation log **without** generating;
5. the response shape for a triggered rail versus a clean pass, to confirm `_detection_names()`
   parses the real payload rather than the assumed one.

**One trap the deployment surfaced, worth knowing before the next attempt:** the CR reported
`DeploymentReady=True` while the Deployment was `0/1` and its pod stuck in `Init`. Read the pod,
not the CR's conditions. (The pod was then evicted for node disk pressure — see memory
`diskpressure-master-cascades-into-mesh`; the NeMo server image is multi-GB and the node it
landed on was already over its threshold.)

## Remaining

1. Redeploy the CR (`nemoGuardrails.enabled: true`) once the cluster has disk headroom, and
   answer questions 2, 3 and 5. `nemoUrl` is already corrected from question 1;
   `_detection_names()` is still written against an assumed payload shape and question 5 is what
   confirms or corrects it.
2. Flip `guardrails.backend` to `nemo` and prove, with the Nemo Service scaled to 0, that a real
   agent turn still returns a complete unmodified response and
   `zuno.guardrails_evaluations{outcome="unavailable"}` increments.
3. Update the `zuno-trustyai` dashboard's detections panel for the widened label set.
4. In the same commit as the flip: delete `DETECTOR_PARAMS` and `PolicyParityWithRails`.

## Verification

```bash
cd components/agent-runtime && ./.venv/bin/python tests/test_guardrails.py   # 18 passing
helm template t gitops/charts/trustyai-config                                # renders nothing
helm template t gitops/charts/trustyai-config \
  --set trustyaiConfig.enabled=true --set nemoGuardrails.enabled=true        # CR + ConfigMap
make d2 check trustyai-config
oc get nemoguardrails,configmap -n zuno-ai-run | grep -i 'guardrails\|nemo-rails'
```
