# ADR-0108: Automate model evaluation with LM-Eval

- **Status:** Partially implemented (gate runner, CI wiring and LMEvalJob manifests merged; the eval itself now runs end-to-end on the GPU cluster, roadmap WP-10). Updated 2026-08-18: three real bugs in the 3.5.0-ea.2 TrustyAI operator were found and fixed live along the way - (1) `outputs.pvcManaged` with no `size` panics the operator's reconciler (`resource.MustParse("")`), now sized explicitly; (2) the served in-cluster model name isn't a valid HF repo id for `AutoTokenizer.from_pretrained`, now overridden via the real `tokenizer` modelArg; (3) `allowOnline: true` and a `spec.pod.container.env` override are BOTH silently ignored by the rendered pod (hardcoded `HF_*_OFFLINE=1`) - worked around with a `datasetCachePvc` (HF_HOME pre-warmed by the operator, one `load_dataset` call per task). That session's 2026-08-18 note called the resulting 503s "a genuine service-mesh routing gap... out of this WP's scope" - **that diagnosis was wrong**, corrected 2026-08-21: `/v1/chat/completions` fails identically from the same pod (disproving the path-specific framing), the predictor itself was healthy throughout (200 OK via loopback, zero requests ever reaching its access log from the eval pod), and the 503's "connection timeout" signature is the standard mark of a `NetworkPolicy` silently dropping the packets, not an mTLS/routing fault. Root cause: `gitops/charts/models/templates/networkpolicy.yaml`'s ingress allow-list only ever listed `ai-gateway`/`rag-service` - WP-10 added the lm-eval workload as a new legitimate caller of the predictor but never added it to the allow-list. Fixed by adding an ingress rule for pods labeled `app.kubernetes.io/name: lm-eval`; also automated the previously-manual `lmeval-hf-cache` PVC prefetch (`pvc-lmeval-cache.yaml`/`job-lmeval-cache-prefetch.yaml`, tokenizer sourced from this cluster's own S3 model bucket rather than huggingface.co) so it no longer needs re-populating by hand each session. Verified live: a full `mmlu_abstract_algebra` run now completes cleanly (100 samples, 400 requests, `acc: 0.57 ± 0.05`, `state: Complete reason: Succeeded` in the driver's own log). Remaining gap keeping this `Partially implemented` rather than `Implemented`: the operator's `LMEvalJob.status.state` field itself stays `Scheduled` and never reflects the real `Complete` state or carries `status.results` (a fourth, real 3.5.0-ea.2 operator bug, distinct from the three above) - `ansible/roles/models/tasks/precheck.yml`'s Day 1 check reads exactly those CR status fields, so `make d1 check models` still won't see this run as complete even though it genuinely succeeded; results are only visible via the pod's own logs/PVC output today. The full `mmlu` group (56,168 requests) still overruns this demo cluster's shared GPU capacity, so `taskNames` stays scoped to the single `mmlu_abstract_algebra` subject.
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
