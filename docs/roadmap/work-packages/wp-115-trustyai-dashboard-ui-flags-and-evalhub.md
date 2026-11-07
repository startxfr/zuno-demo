# WP-115: TrustyAI in the RHOAI dashboard - feature flags and the EvalHub instance

- **State:** Done (2026-11-07, with a recorded vendor limitation) - the Evaluations page works end to end on RHOAI
  3.6.0-ea.2 up to the call to the model (RBAC, collections, providers, tokenizer, dataset, job); the score itself is
  blocked by an EvalHub x KServe defect, see "Closure (2026-11-07)" below
- **ADRs:** [ADR-0534](../../adr/0534-integrate-trustyai-for-ai-evaluation-and-guardrails.md)
- **Depends on:** WP-113 (Done - the Grafana surface this complements)
- **Related:** [ADR-0538](../../adr/0538-adopt-rhoai-35-workload-surfaces-mlflow-kueue-trainingjobs.md)
  (the sibling effort for the other three dashboard pages)

## Goal

WP-113 gave the TrustyAI chain a Grafana dashboard, and the human live test passed - but the
operator then asked the obvious follow-up: why is none of this visible in the **RHOAI
dashboard** itself? Investigation found two distinct causes, both fixed here:

1. **The dashboard hides its TrustyAI pages by default.** `OdhDashboardConfig/
   odh-dashboard-config` (operator-created, NOT in this repo) ships `disableLMEval` unset and
   `guardrails` unset on this release train, so the Evaluations and guardrails surfaces never
   render. Only the unrelated "Model monitoring bias" card (the predictive `TrustyAIService`,
   deliberately unconfigured per ADR-0534) was visible - actively misleading.
2. **The Evaluations page needs a per-project evaluation service.** With the flag on, the page
   rendered "Evaluations unavailable - enable the evaluation service using the TrustyAI
   Operator": the operator's EVALHUB controller had been running since install (WP-108 finding
   #2) but no `EvalHub` CR ever existed.

## Steps

### Step 1 - dashboard feature flags (live patch, documented not committed)
`oc patch odhdashboardconfig odh-dashboard-config -n redhat-ods-applications --type merge`
with `disableLMEval: false` and `guardrails: true`. This CR is operator-created and outside
GitOps; ADR-0534's Operational considerations carries the authoritative flag list.

### Step 2 - the EvalHub instance
`gitops/charts/trustyai-config/templates/evalhub.yaml` + `evalHub` values block: sqlite
backend (demo-light), 4 OOTB collections (`standard-llm-evals-v1`, `safety-and-fairness-v1`,
`reasoning-v1`, `leaderboard-v2`) and 2 providers (`lm-evaluation-harness`, `garak`), names
matching the operator ConfigMaps' `evalhub-collection-name`/`evalhub-provider-name` labels.

### Step 3 - a real evaluation run from the UI
Drive the wizard end to end against a live model and confirm the run appears with results -
the acceptance proof that the surface is not merely rendered but functional.

## Live findings (2026-09-02, execution)

1. **The flags were the whole first problem** - both applied cleanly, persisted across an
   operator reconcile, and the nav gained Evaluations/Experiments/Jobs immediately, with no
   `rhods-dashboard` restart needed (they are read per-request).
2. **EvalHub crashed on its first deploy with `Failed to setup OTEL: Not implemented`** - this
   ea build's server exits when an `otel` block is present, even though the CRD documents the
   field. Dropped the block (the CRD's own default is OTEL-disabled); the instance then reached
   `Ready=True` (v0.4.3). Commits `932abb63` (instance) and `365c8252` (the OTEL fix).
3. **EvalHub runs are plain `batch/v1` Jobs, NOT LMEvalJobs** (its ServiceAccount has
   `batch/jobs: create` and no `lmevaljobs` RBAC at all). Consequence worth knowing: the three
   ArgoCD-managed `LMEvalJob`s from WP-107/WP-109, and the garak/ragas Jobs, are a **parallel
   path** and will never appear in this page's run list - the dashboard shows only what EvalHub
   itself launched.
4. The page offers **197 benchmarks** across the 4 collections, and EvalHub reads the cluster's
   `HardwareProfile`s (`mig-1g-24gb`, `mig-2g-48gb`) as the intended resource-override path -
   the provider defaults request no GPU.

## What NOT to touch

- The "Model monitoring bias" card / `TrustyAIService` - stays unconfigured by ADR-0534
  decision.
- `mcpGuardrailsMode` - stays `false` (WP-108 proved the flip kills LM-Eval).
- The existing ArgoCD-managed LMEvalJob/garak/ragas path - it is the automated evidence chain;
  EvalHub runs are the interactive complement, not a replacement.

## Verification checklist (operator step - ask before running)

1. Both flags readable on the live `OdhDashboardConfig`, nav entries present after refresh.
2. `oc get evalhub zuno-evalhub -n zuno-ai-run` reports `Ready=True` with the 4 collections and
   2 providers in `status.activeCollections`/`activeProviders`.
3. A UI-launched evaluation run creates a Job in `zuno-ai-run`, completes, and its result is
   visible on the Evaluations page.
4. `make d3 check trustyai-config` still fully green.

## Risks and known unknowns

1. sqlite backend: the EvalHub run history lives in the pod and does not survive a restart -
   acceptable for a demo surface, upgradeable to postgresql (the CRD supports a `db-url`
   Secret) if run history ever needs to persist.
2. The model endpoint given to a run must be the **plain-http in-cluster** URL
   (`http://<model>-kserve-workload-svc.zuno-ai-run.svc:8000/v1`) - https there re-triggers the
   [[lmevaljob-mesh-double-tls]] failure that broke the LM-Eval gate for a week.

## Status updates (once live-verified)

- `State` moves to `Done` once checklist items 1-4 pass, including a real UI-launched run.

## Update (2026-11-07) - RHOAI 3.6: the personas had no right to use the page

Three things stood between the personas and a UI-launched run on RHOAI 3.6.0-ea.2:

1. The RHOAI dashboard itself answered 404 on `rh-ai.<domain>` (portal hostname route, fixed under WP-220's update
   of the same date).
2. A browser that had loaded the page before the upgrade kept a stale `/_mf/evalHub/remoteEntry.js` (the module server
   answers 304 to a later `If-Modified-Since`) and asked for a chunk the new module does not have: `ChunkLoadError`.
   A hard refresh fixes it; nothing on the cluster.
3. RBAC: the eval-hub-ui BFF lists EvalHub CRs as the user, and the EvalHub server authorizes each call with a
   SubjectAccessReview on `trustyai.opendatahub.io` collections/providers/evaluations (and `mlflow.kubeflow.org`
   experiments on job creation). The vendor grants evalhubs read only in redhat-ods-applications, and admin/edit
   aggregate none of it, so ai-ops-01 (admin of zuno-ai-run) saw nothing. New
   `templates/evalhub-user-rbac.yaml` (`evalHub.userGroups`: ocp-ai-ops, ocp-ai-dev): live 2026-11-07, SARs allow
   collections/providers list, evaluations list/create and experiments create; providers create stays refused.


## Closure (2026-11-07) - six UI-launched runs, closed with a vendor limitation

Six runs launched by ai-dev-01 from the Evaluations page (project zuno-ai-run, external endpoint
`http://qwen35-9b-kserve-workload-svc.zuno-ai-run.svc:8000/v1`), each failure removing one cause:

| Run | Failure | Cause and action |
|---|---|---|
| 1 | cannot reach huggingface.co | zuno-ai-run EgressFirewall (WP-224 rehearsal) is deny-all; HF hosts opened for the test only |
| 2 | `qwen3.5-9b` is not a valid HF id | the tokenizer defaults to the model name; vLLM serves `qwen3.5-9b` (not `qwen35-9b`) |
| 3 | tokenizer.json download timeout | HF serves it from the Xet CDN `us.aws.cdn.hf.co`; added for the test |
| 4 | connection reset on :8000 | per-model NetworkPolicy admits only ai-gateway, MaaS gateway, monitoring; `templates/networkpolicy-evalhub-clients.yaml` (models chart) admits the instance's evaluation-job pods |
| 5 | pod stuck in Init | mesh CA down during the WP-223 Vault migration (vault-issuer-istio CA bundle), fixed by that window |
| 6 | 502 / connection reset on :8000 | **vendor defect, not fixable from the EvalHub CR** |

Run 6's cause: EvalHub job pods set `automountServiceAccountToken: false` and mount the SA token only into the
`sidecar` and `adapter` containers. The DestinationRule that KServe generates for every LLMInferenceService
workload Service (`<model>-kserve-workload-svc`, `tls.mode: SIMPLE`) points Envoy at
`caCertificates: /var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt`, which does not exist in the job pod's
`istio-proxy`, so the TLS origination fails and the connection is reset. A throwaway meshed pod with the same labels
and the default token mount got HTTP 200 on `/v1/models` and `/v1/completions` three times out of three. The EvalHub
CR offers no pod annotation, label or automount knob. To report upstream (EvalHub job pod template or KServe DR).

Benchmark parameters that work in the form: `{"tokenizer": "Qwen/Qwen3.5-9B", "num_examples": 10}`, model name
`qwen3.5-9b`. A run behind the zuno-ai-run firewall also needs `huggingface.co`, `us.aws.cdn.hf.co` (Xet) and, for
ifeval, `raw.githubusercontent.com` (NLTK punkt_tab); those hosts were removed after the test and are not in git.
`make d3 check trustyai-config`: green (2026-11-07). Checklist items 1, 2 and 4 pass; item 3 (run completes with a
result) is the vendor limitation above.
