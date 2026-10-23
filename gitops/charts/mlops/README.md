# mlops

OpenShift AI dataset-to-model MLOps pipeline (ADR-0301/ADR-0302, WP-34).
Uses the `DataSciencePipelinesApplication`/KFP mechanism (ADR-0330, since
retired with the retired rag-ingestion) with a per-candidate-agent map (`values.yaml`'s
`agents:`), since every mlops run takes an agent identity as its run-target.

## Runtime image / CLI stages

`components/mlops/src/mlops.py` implements four stages, one command
contract, single image for every KFP task (one image for every task):

- `prepare-dataset` - trains on a style corpus (ADR-0526); the former
  domain-grounding read of `document_embeddings` left with rag-service
  (WP-168) and fails loudly if a run still declares knowledge domains. Also reads
  the target agent's own `evaluations/<agent>/scenarios.yaml` chat-shaped
  scenario messages (a stand-in for "real usage logs" until this demo
  environment has live traffic). Writes `examples.jsonl` +
  `dataset_manifest.json` to S3, classification escalated (never
  downgraded) from every contributing source.
- `train-lora` - real PEFT/LoRA fine-tuning (`torch`/`transformers`/
  `peft`/`datasets`, imported lazily so no other stage needs them
  installed) of the configured base model on the prepared dataset, saved
  and uploaded to S3. `MLOPS_CPU_SAFE=true` forces a tiny, real (not
  mocked) training run - one epoch, five steps, no GPU required - the
  "training code path exercised with a tiny CPU-safe config" WP-34's own
  brief asks for; unset targets a real GPU run (the operator's own step -
  this repository's sandbox has no GPU to run it in).
- `evaluate` - runs the target agent's own `evaluations/<agent>/
  quality_gate.py` (ADR-0107), which subprocess-invokes
  `run_acceptance_gate.py` (the agent's real 20-scenario/security-checks/
  gate-checks suite) and re-derives PASS/FAIL from that agent's own
  `gate_config.yaml` threshold - never a parallel evaluation harness
  (ADR-0302 point 5). Fails the KFP task (non-zero exit) when the gate
  does not PASS, stopping the DAG before `push-registry` ever runs.
- `push-registry` - registers a PASSING adapter in the OpenShift AI Model
  Registry (RegisteredModel -> ModelVersion -> ModelArtifact, the
  `kubeflow/model-registry` v1alpha3 REST API). Independently re-checks
  the gate result itself before making any request - the second,
  independent enforcement of ADR-0302's "no bypass" requirement. **Never
  writes to `gitops/charts/models/values.yaml`** - promotion to serving
  stays a human-reviewed GitOps PR (ADR-0302 point 7).

`components/mlops/tests/test_mlops.py` exercises every stage against
fakes/mocks (in-memory S3, mocked Postgres/HTTP/training calls) - see
that file's own module docstring.

## Resources this chart renders

- `DataSciencePipelinesApplication` (`mlops-dspa`) - KFP v2 server,
  S3-backed object storage, embedded MariaDB metadata store by default.
- One `Pipeline` CR (`mlops`) registering the pipeline's identity in KFP.
- `pipeline.py` KFP SDK source (`files/pipeline.py.tpl`, rendered into a
  ConfigMap) - one `@dsl.pipeline` DAG per enabled candidate agent
  (`values.yaml`'s `agents:` map; Comage is the only one enabled today,
  ADR-0301 point 5's own starting candidate), each chaining
  prepare-dataset -> train-lora -> evaluate -> push-registry via
  `.after()`. **Not yet compiled/uploaded by anything in this repo** -
  same currently-unfinished gap `the retired rag-ingestion`'s own chart documents
  (`values.yaml`'s `images.compiler` comment there); a future compile-time
  step is required before an actual KFP run can be submitted from this
  source. Until then, the ConfigMap serves as the checked-in,
  version-controlled DAG definition an operator compiles locally
  (`pip install kfp kfp-kubernetes` + `python pipeline.py comage` -
  `kfp-kubernetes` is required, the DAG uses its
  `add_node_selector`/`add_toleration`/secret/ConfigMap helpers) or via a
  follow-up automated step. Since ADR-0351 the train-lora task requests a
  whole `nvidia.com/gpu` plus the `zuno.io/gpu-burst` toleration
  (`values.yaml`'s `training:` block): a submitted run triggers the
  scale-from-zero burst GPU node (`gitops/charts/machines`) and trains on
  its full 96GB card, and the node is reclaimed ~10min after the stage
  ends.
- One env ConfigMap per enabled agent (`templates/agent-configmaps.yaml`)
  - `MLOPS_AGENT`/knowledge-domains/base-model/LoRA hyperparameters baked
    in per candidate; `MLOPS_RUN_ID` is deliberately NOT here since it
    varies per pipeline run (passed as a `--run-id` CLI argument instead,
    a KFP pipeline parameter substituted at run-submission time).
- `ExternalSecret`s for S3 (`s3.externalSecret`, same bucket/credential
  as the platform's data bucket, ADR-0302 point 3) and, only when
  `postgres.enabled` (off), read-only Postgres access
  (`postgres.externalSecret`; this pipeline never writes to Postgres).
- `ServiceAccount`/`Role`/`RoleBinding` (no Kubernetes API access needed
  - `kfp-kubernetes` injects Secrets/ConfigMaps directly) and
  `NetworkPolicy` (default-deny ingress on every KFP component pod, same
  as the other KFP charts).

## Not covered by this chart

- Compiling `pipeline.py` and uploading the result to the DSPA/KFP API -
  see the `pipeline.py` bullet above.
- Running the pipeline itself - an operator action, needs a real GPU node
  and real Model Registry/S3/Postgres credentials.
- The Model Registry instance itself (`gitops/charts/openshift-ai`'s
  `modelregistry` OpenShift AI component, `managementState: Managed`) -
  this chart only calls its REST API, never deploys it.
