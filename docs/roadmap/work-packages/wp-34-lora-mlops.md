# WP-34: LoRA serving and the MLOps pipeline

- **State:** Not started
- **ADRs:** ADR-0302 then ADR-0301 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-33 part (a) (Comage bundle = first training target), WP-10 (quality gate)
- **Blocks:** WP-39, WP-40
- **Estimated files touched:** Part A ~12, Part B ~4 (two PRs: pipeline first, serving second)

> Execute this brief as a standalone task from the repository root. Read
> both ADRs fully — their numbered Decision points are the specification;
> both defer acceptance criteria to the Standard clauses (merged via review,
> docs updated, `make check`/component tests demonstrate behavior).

## Goal

Part A (ADR-0302): a KFP pipeline — dataset prep from evaluation transcripts
+ RAG store, LoRA/PEFT training, ADR-0027/0028 evaluation gate, Model
Registry push — scaffolded on the existing `ansible/roles/mlops` day1
component with a new `mlops_build` role and `components/mlops/` source.
Part B (ADR-0301): serve registered adapters through the existing vLLM
ServingRuntime with native multi-LoRA, statically selected in
`gitops/charts/models/values.yaml`. GPU cluster runs are the operator part.

## ADR references

- [docs/adr/0302-build-dataset-to-model-mlops-pipelines.md](../../adr/0302-build-dataset-to-model-mlops-pipelines.md)
  — numbered points 1–7; KFP runs on the existing
  `DataSciencePipelinesApplication`/aipipelines component (ADR-0330's
  pattern); datasets come from `evaluations/<agent>/` transcripts +
  `document_embeddings`, S3-staged per ADR-0330; the eval gate is the
  target agent's 20 scenarios at 75% via
  `evaluations/<agent>/run_acceptance_gate.py`; registry push targets the
  OpenShift AI Model Registry (`modelregistry.registriesNamespace:
  zuno-ai-build`, already Managed). **Promotion is a human-reviewed GitOps
  PR updating `gitops/charts/models/values.yaml` — the pipeline never
  pushes to serving.** (Component/role naming and mirroring are in Part A
  below.)
- [docs/adr/0301-introduce-lora-and-peft-model-customization.md](../../adr/0301-introduce-lora-and-peft-model-customization.md)
  — numbered points 1–5; vLLM native multi-LoRA is additive on the existing
  `vllm-runtime` ServingRuntime, NOT a second InferenceService per adapter;
  adapter selection is static in values (dynamic selection is
  ADR-0303/WP-39); adapters referenced by registry name/version per
  ADR-0115; first candidate is Comage; rollback = edit values + ArgoCD
  sync. (Values/flag wiring and classification gating are in Part B below.)

## Preconditions (verify before starting)

- WP-33 part (a) merged (`agents/comage/` real bundle); WP-10 merged
  (`evaluations/quality_gate.py`).
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `ansible/roles/mlops/tasks/precheck.yml` (the placeholder this WP
  replaces), `ansible/roles/rag_ingestion/` + `rag_ingestion_build/` (the
  role pair to mirror), `ansible/tasks/apply_openshift_build.yml`,
  `gitops/charts/models/values.yaml` (`servingRuntimeName: vllm-runtime`,
  `image.vllm`), `gitops/charts/openshift-ai/values.yaml` (modelregistry
  block), `components/rag-ingestion/` (S3-staged KFP stage pattern).

## Part A — repo changes (ADR-0302)

1. `components/mlops/`: pipeline source mirroring `components/rag-ingestion/`
   layout — staged CLI (`prepare-dataset`, `train-lora`, `evaluate`,
   `push-registry`), S3 state round-trip between stages, Containerfile.
   `prepare-dataset` reads evaluation transcripts + selected
   `document_embeddings` content (no new data-collection surface);
   `train-lora` parameterized by agent/base model (PEFT config); `evaluate`
   invokes the WP-10 gate against the candidate; `push-registry` registers
   the passing adapter (name/version) in the Model Registry API. Unit tests
   with fixtures; no GPU in CI (training code path exercised with a tiny
   CPU-safe config).
2. `ansible/roles/mlops_build/`: mirror `rag_ingestion_build`; add `mlops`
   to `DAY1_BUILD_COMPONENTS` in the `Makefile` and the build playbook's
   component list. (Note: the Makefile is in the ADR-0344 dirty set — if
   still uncommitted, stop and ask.)
3. `ansible/roles/mlops/`: replace the precheck placeholder with real
   install/check tasks (KFP pipeline upload + recurring/manual run, DSPA
   checks) mirroring `ansible/roles/rag_ingestion/tasks/`; make
   `make d1 check mlops` meaningful per the ADR's operational note.
4. Build matrix: add the `components/mlops/` image to
   `.github/workflows/build-publish.yml` (check_build_matrix gate).

## Part B — repo changes (ADR-0301)

5. `gitops/charts/models`: enable multi-LoRA on the vLLM runtime
   (`--enable-lora`; `loraAdapters:` values list of registry name/version
   entries rendered into `--lora-modules`), additive and default-empty;
   adapter classification annotation per ADR-0034/0021 with a values-schema
   check that a C2/C3 adapter cannot be attached to a serving path declared
   external-eligible.
6. Extend `make d1 check models` (via `ansible/roles/models`) to assert
   declared adapters are loaded/healthy.

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set
  (**Makefile is in it** — coordinate before editing).
- The pipeline must never write to `gitops/charts/models/values.yaml`
  (human-reviewed PR only — ADR-0302 point 7).
- `evaluations/*/scenarios.yaml` content; `gitops/apps/*` `targetRevision`;
  immutable-tag rule applies to the new image (post-WP-04).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/mlops/ -q`
- `python3 platform/supply-chain/check_build_matrix.py` (exit 0)
- `helm lint gitops/charts/models`; `helm template` renders `--enable-lora`
  when an adapter is listed and omits it when the list is empty
- `ansible-playbook ansible/playbooks/day1_build.yml --syntax-check` and
  `day1_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: `make d1 build mlops`, then run the pipeline on the GPU cluster
   for the Comage candidate; confirm dataset → train → gate → registry.
2. User + operator: review the promotion PR the pipeline outputs artifacts
   for; merge; sync; `make d1 check models` proves the adapter serves.

## Status updates (then re-run check_docs.py)

- After Parts A+B merge: both ADRs →
  `Partially implemented (pipeline, roles, serving configuration and tests merged; GPU pipeline run and adapter promotion pending)`;
  index rows to match; tracker → `Operator pending`.
- After the GPU run + promotion: ADR-0302 →
  `Implemented - see \`components/mlops/\`, \`ansible/roles/mlops/\`.`;
  ADR-0301 → `Implemented - see \`gitops/charts/models/\`.`; index rows
  `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Dynamic per-request adapter selection (WP-39 / ADR-0303).
- Routing-policy optimization + continuous benchmarking (WP-40 / ADR-0304/0305).
