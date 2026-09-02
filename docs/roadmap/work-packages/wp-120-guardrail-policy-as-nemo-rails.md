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

- `gitops/charts/trustyai-config/files/nemo-rails/observe/{config.yml,rails.co,actions.py}` —
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

## The live discovery gate — not yet run

ADR-0540's design answers the cost question by construction (no `models:` block, so no
inference), but five things about the operand cannot be read from the CRD and must be
established from an `agent-runtime` pod before `guardrails.backend` is flipped:

1. the Service name and port the operator creates for the CR — `guardrails.nemoUrl` currently
   assumes the `<cr-name>-service` convention `detectorUrl` already follows;
2. whether `GET /v1/rails/configs` lists `zuno-observe`;
3. whether `POST /v1/chat/completions` with `options.rails: ["input"]` and
   `log.activated_rails: true` returns the activation log **without** generating;
4. whether a config with no `models:` block validates and starts at all;
5. the response shape for a triggered rail versus a clean pass, to confirm `_detection_names()`
   parses the real payload rather than the assumed one.

If (4) turns out to require a model, the observe-only path becomes a GPU-backed inference call
per exchange on a cluster whose quota is saturated. That is a cost decision to escalate, not to
absorb — see ADR-0540's Decision 2.

## Remaining

1. Run the discovery gate above; correct `nemoUrl` and `_detection_names()` against what the
   operand actually returns.
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
