# ADR-0108: Automate model evaluation with LM-Eval

- **Status:** Partially implemented (gate runner, CI wiring and LMEvalJob manifests merged; GPU cluster runs pending, roadmap WP-10). Updated 2026-08-18: three real bugs in the 3.5.0-ea.2 TrustyAI operator were found and fixed live along the way - (1) `outputs.pvcManaged` with no `size` panics the operator's reconciler (`resource.MustParse("")`), now sized explicitly; (2) the served in-cluster model name isn't a valid HF repo id for `AutoTokenizer.from_pretrained`, now overridden via the real `tokenizer` modelArg; (3) `allowOnline: true` and a `spec.pod.container.env` override are BOTH silently ignored by the rendered pod (hardcoded `HF_*_OFFLINE=1`) - worked around with a `datasetCachePvc` (HF_HOME pre-warmed by the operator, one `load_dataset` call per task) since HF's offline mode only blocks network calls, not reads from an already-populated cache. The full `mmlu` group (56,168 requests) also overran this demo cluster's shared GPU capacity mid-run (real 503s from the predictor); rescoped to the single `mmlu_abstract_algebra` subject task. All of the above landed and got a real request past every one of those layers - but the run itself could not complete: `POST /v1/completions` on the qwen predictor consistently 503s after ~10s with an Envoy/ztunnel-origin "upstream connect error... connection timeout", while `/v1/chat/completions` on the exact same pod/port serves normally. This is a genuine service-mesh routing gap for the OpenAI legacy completions path specifically (`local-completions`, the model type `lm_eval`'s loglikelihood-based tasks require) - not a chart or operator defect, out of this WP's scope to fix. Stays `Partially implemented`; the scratch dataset-cache PVC (`lmeval-hf-cache`) was deleted at end of session and needs re-populating per `gitops/charts/models/values.yaml`'s dated comment before the next attempt.
- **Target:** v0.1
- **Date:** 2026-08-14
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.1-roadmap entry
(`0100-v0.1-roadmap.md`) to a full record.

Use OpenShift AI's LM-Eval capability (`LMEvalJob` resources on the
DataScienceCluster's evaluation component) to benchmark candidate local
models on declared task suites before they become routable (ADR-0021
classes). Job manifests and task selections are GitOps-managed; results
land in the model quality gate (ADR-0107) as one of its inputs. LM-Eval
complements — never replaces — the per-agent ADR-0027 acceptance suites.

See [Standard clauses](README.md#standard-clauses) for Alternatives
considered, Consequences, Security/Operational considerations,
Acceptance criteria and Review evidence.

## Related ADRs

- [ADR-0019](0019-use-openshift-ai-model-serving-for-local-inference.md)
- [ADR-0021](0021-route-models-according-to-c1-c2-c3-classification.md)
- [ADR-0107](0107-introduce-automated-model-quality-gates.md)
