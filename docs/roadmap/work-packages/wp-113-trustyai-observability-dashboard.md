# WP-113: TrustyAI observability dashboard (Grafana surface for the evaluation/guardrails chain)

- **State:** Not started (2026-09-02)
- **ADRs:** [ADR-0534](../../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)
  (primary), [ADR-0413](../../adr/0413-consolidate-grafana-dashboards-into-six-platform-views.md)
  (dashboard conventions), [ADR-0029](../../adr/0029-instrument-model-usage-costs-and-distributed-traces.md)
  (OTLP-push metrics pattern)
- **Depends on:** WP-109 (Done - the chain this WP makes visible)
- **Related:** WP-107/WP-108 (the `trustyai-config` component this extends)

## Goal

WP-107/108/109 closed with the full TrustyAI chain live-verified - but only via CLI (`oc`,
`make d3 check`, log greps). The human live test of ADR-0534 failed on exactly that point: an
operator opening the platform's UIs sees **nothing** of TrustyAI. The RHOAI dashboard's only
TrustyAI surface (the "Model monitoring bias" card) configures a `TrustyAIService` - predictive
bias monitoring, deliberately out of ADR-0534's generative scope - and every real artifact
(LMEvalJobs, guardrails detections, Garak/RAGAS runs) is invisible in both the RHOAI dashboard
and Grafana.

This WP gives the chain a real observability surface: guardrails and evaluation results become
Prometheus series pushed through the platform's standard OTLP pipeline, rendered on a new
`zuno-trustyai` Grafana dashboard. Full scope was chosen over a kube-metrics-only minimum by
explicit user decision (2026-09-02), as was NOT configuring the RHOAI bias-monitoring card.

## What becomes visible

| Signal | Source | Metric |
|---|---|---|
| Guardrails exchanges observed | agent-runtime (new meter) | `zuno_guardrails_evaluations_total{agent}` |
| Guardrails detections | agent-runtime (new meter) | `zuno_guardrails_detections_total{agent, detection}` |
| RAGAS scores | `ragas_eval.py` end-of-run push | `zuno_ragas_score{metric, question}` |
| Garak attack success rate | garak Jobs end-of-run push | `zuno_garak_attack_success_rate{probe, detector}` |
| Eval Job outcomes | kube-state-metrics (existing) | `kube_job_status_succeeded/failed` |
| LMEval pod activity | kube-state-metrics (existing) | `kube_pod_status_phase` |

LMEvalJob `status.results` (the benchmark scores themselves) stays CLI-only: no CR-field-to-
Prometheus exporter exists on this platform and building one is out of this WP's scope.

## Steps

### Step 1 - guardrails metrics in agent-runtime
Add a `MeterProvider` to `components/agent-runtime/app/telemetry.py` (mirror
`components/ai-gateway/app/telemetry.py`; model-call metrics deliberately stay in ai-gateway,
per that file's docstring - guardrails counters are agent-runtime's own). Increment both
counters in `components/agent-runtime/app/clients/guardrails_client.py`'s `_evaluate`; the
never-raise, observe-only contract is unchanged (metric failure must never affect a response).
Extend `components/agent-runtime/tests/test_guardrails.py`. Push before the in-cluster build.

### Step 2 - RAGAS and Garak score push
`components/trustyai-eval/ragas_eval.py` gains a best-effort end-of-run OTLP/HTTP JSON POST
(httpx is already in the image) to the collector
(`http://zuno-otel-collector-collector.zuno-monitoring.svc:4318/v1/metrics`). The garak Jobs in
`gitops/charts/trustyai-config/templates/` gain a small inline python step parsing the report
and pushing ASR the same way. A push failure logs and exits 0 - it never fails the Job.

### Step 3 - NetworkPolicy verification
Verify live that the collector's ingress (zuno-monitoring) admits these pods from zuno-ai-run;
extend the allow if the `lm-eval`-labelled Jobs are not covered. Never a new Envoy port
exclusion without its matching NetworkPolicy.

### Step 4 - the `zuno-trustyai` Grafana dashboard
New `gitops/charts/grafana/templates/dashboard-trustyai.yaml`: uid `zuno-trustyai`, folder
"Zuno Platform", sync-wave 26, classic schemaVersion 39 with `row` panels (the v2 schema is
rejected by grafana-operator v5.24.0), explicit `{"type":"prometheus","uid":"prometheus"}` on
every target. Three rows: Guardrails (observe-only), Evaluation jobs, Scores.

### Step 5 - live test and human sign-off
Re-run the eval Jobs, replay a jailbreak+PII chat, verify the new series in Thanos and the
populated panels in a browser, then ask the operator for the human live test verdict. If OK,
record the dated human sign-off in ADR-0534.

## What NOT to touch

- The RHOAI "Model monitoring bias" card / `TrustyAIService` CR - stays unconfigured by
  decision; ADR-0534 documents why.
- `mcpGuardrailsMode` - stays `false` (WP-108 proved the flip kills LM-Eval).
- The observe-only contract - no metric, timeout or push may ever alter a delivered response.
- `monitoring.rhobs/v1` - any monitoring CR must be `monitoring.coreos.com/v1`.

## Verification checklist (operator step - ask before running)

1. A real chat exchange increments `zuno_guardrails_evaluations_total` (and a jailbreak/PII one
   `zuno_guardrails_detections_total`) queryable via Thanos.
2. A fresh `ragas-eval` run lands `zuno_ragas_score` series; a fresh garak security run lands
   `zuno_garak_attack_success_rate`.
3. The `zuno-trustyai` dashboard renders in Grafana with all three rows populated.
4. `make d3 check trustyai-config` still fully green; agent chat behavior unchanged.
5. Human live test verdict collected; if OK, sign-off recorded in ADR-0534.

## Risks and known unknowns

1. OTLP/HTTP JSON hand-rolled from the eval Jobs (no SDK in the garak image) - schema mistakes
   fail silently at the collector; verify series existence, not just HTTP 200.
2. Metric cardinality: `question` and `probe`/`detector` labels are small and bounded here, but
   keep them enumerable - no free-text labels.
3. The collector's Prometheus exporter drops metrics with stale timestamps on one-shot pushes -
   if scores don't appear, check collector logs before suspecting the Jobs.

## Status updates (once live-verified)

- This WP's `State` moves to `Done` once the checklist passes and the human live test verdict is
  recorded. ADR-0534 stays `Implemented` throughout; only its notes gain the visibility
  clarification and (if OK) the human sign-off.
