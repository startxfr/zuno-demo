# WP-087: Train, serve and route the French urban-register model variant (`-wesh`)

- **State:** Done (2026-08-29) — run `wesh-20260829-145123` reached `overall: PASS` on all three gate halves and `push-registry` SUCCEEDED, registering `comage-lora` version `wesh-20260829-145123` (model_version_id 6). Parts A–F merged, plus fourteen execution fixes that only real runs could expose. Two findings outlive the WP and are recorded in ADR-0526's amendment: routing Comage to the variant broke its tool calling (0 tool-call examples in a 908-conversation corpus), fixed by 62 two-sided examples and now gated by a third half; and the hallucinated-tool ceiling of 10% is met by neither the variant (7.4%) nor its unmodified base (11.1%). Still untested: the fallback behaviours — Comage when the variant is unavailable, Tekos on either path
- **ADRs:** ADR-0526 (Proposed → Implemented). Supersedes in part ADR-0301 (decisions 1, 5) and ADR-0302 (decisions 2, 4).
- **Depends on:** WP-34 (the `components/mlops/` CLI and `gitops/charts/mlops/` this WP fixes and extends), WP-076 (the MaaS per-model recipe), WP-083/WP-086 (the second permanent MIG node and the soft anti-affinity)
- **Replaces the objective of:** WP-34 (`comage-lora` domain adaptation — never run, and its two knowledge domains hold zero rows)
- **Blocks:** WP-39, WP-40
- **Estimated files touched:** ~28

> Execute this brief as a standalone task from the repository root. Read
> ADR-0526 fully — its nine numbered Decision points are the specification.

## Goal

Make the mlops pipeline produce `qwen3.5-9b-wesh` — a LoRA fine-tune of
`Qwen/Qwen3.5-9B` on the staged French urban-register corpus, merged into a
standalone bf16 checkpoint — serve it beside its unmodified base on a different
GPU node, and re-route Comage (first choice, all tasks) and Tekos (second choice,
all tasks) to it. No new node, no quota change.

## Why

The pipeline WP-34 merged has **never executed**: the `Pipeline` CR `mlops` in
`zuno-mlops` carries **0 versions and 0 runs**. Two things kept it there — nothing
in the repository compiles or uploads a `PipelineVersion`, and the objective it
was built for has no data (Comage's `knowledge.sales` → `rag-sales`, 0 rows;
`knowledge.project` → no `document_embeddings` table at all). This WP fixes the
first and replaces the second with an objective whose corpus exists.

## ADR references

- [ADR-0526](../../adr/0526-fine-tune-and-serve-a-french-urban-register-model-variant.md)
  — decisions 1-9. Decision 3 is the deliberate new data surface; decision 4 is
  the merged-weights reversal of ADR-0301's recorded rejection; decision 8 is the
  two-halves gate.
- [ADR-0521](../../adr/0521-route-local-model-traffic-through-maas.md) decisions 5-6
  — the per-model MaaS manifest set both new models inherit.
- [ADR-0351](../../adr/0351-share-rtx-pro-6000-gpus-via-nvidia-mig-with-scale-from-zero-burst-capacity.md)
  decision 4 (burst training path, reused unchanged) and decision 5 (whose
  single-node survivability property this WP gives up — see ADR-0526 Consequences).

## Preconditions (verify before starting)

- `s3://zuno-corpus/qwen-wesh-training-corpus.tgz` is present (53 KB;
  `qwen-urban-fr-corpus/` with `train.jsonl` 716, `validation.jsonl` 113,
  `test.jsonl` 79, `README.md`, `build_dataset.py`).
- `s3://zuno-demo-rag-corpus/models/qwen3.5-9b/` holds a complete bf16 checkpoint
  (13 objects, 19.3 GB, self-consistent `model.safetensors.index.json`).
- `oc get resourcequota zuno-ai-run-gpu-cap -n zuno-ai-run` still shows
  `requests.mig-1g.24gb: 2/3` and `requests.mig-2g.48gb: 1/2`. If not, stop and
  re-derive placement — this WP consumes the remainder exactly.
- `python3 platform/docs/check_docs.py` exits 0.
- Read: `components/mlops/src/mlops.py`, `gitops/charts/mlops/files/pipeline.py.tpl`,
  `ansible/roles/rag_ingestion/tasks/compile_pipeline_version.yml` (the task mlops
  lacks), `gitops/charts/models/templates/llminferenceservice-gptoss.yaml` (the
  nested-values template to copy), `platform/ai-gateway/provider-routing.yaml`
  header comment (the `-maas`-before-direct pairing rule).

## Repo changes

### Part A — pipeline source (`components/mlops/`)

1. **New dataset source.** Add `MLOPS_STYLE_CORPUS_S3URI`. `prepare-dataset`
   downloads and untars the archive, reads `train.jsonl` + `validation.jsonl`,
   and renders each conversation through the tokenizer's chat template. Carry
   `test.jsonl` forward for Part E. Classification is **C1** — the corpus adds no
   business content, so the existing escalate-only rule leaves it at C1.
2. **Fix the model loading — it cannot work today.** `mlops.py:452-473` uses
   `AutoModelForCausalLM` and a `LoraConfig` with no `target_modules`. The staged
   checkpoint declares `Qwen3_5ForConditionalGeneration` / `model_type: qwen3_5`,
   and its weight map is `model.language_model.layers.*` with **mixed attention**
   — `self_attn.{q,k,v,o}_proj` on the 8 `full_attention` layers,
   `linear_attn.in_proj_qkv`/`out_proj` on the 24 `linear_attention` layers —
   plus an `mtp.*` multi-token-prediction head and a vision tower. Use an `Auto*`
   class that maps this architecture, set `target_modules` explicitly, and
   exclude `mtp.*` and the vision tower.
3. **New `merge-export` stage.** `merge_and_unload()`, `save_pretrained` in bf16,
   `tokenizer.save_pretrained`, then upload to
   `s3://zuno-demo-rag-corpus/models/qwen3.5-9b-wesh/` — the bucket/prefix
   `gitops/charts/models`' `modelsS3` already serves every model from. Extend the
   DAG in `gitops/charts/mlops/files/pipeline.py.tpl` with the matching task
   (only `train-lora` carries the GPU request; this stage does not need one).
4. **Fix `push-registry`.** The default base URL
   `modelregistry-sample.rhoai-model-registries.svc:8080` exists nowhere. The
   real Service is `zuno` in `rhoai-model-registries`, port **8443, HTTPS**
   (Route `zuno-rest.apps.demo222.startx.fr`). Add TLS trust and the
   `Authorization` header the current code has no notion of.
5. **Fix the Postgres wiring in `gitops/charts/mlops/values.yaml`.** `schema:
   public` is wrong — the table is `rag.document_embeddings`, so
   `SET search_path TO public, public` makes `prepare-dataset` fail with
   *relation does not exist* the moment any grounding domain is requested.
6. Extend `components/mlops/tests/` (fakes/mocks only, no live S3/PG/registry/GPU).

### Part B — compile and upload the `PipelineVersion`

This is why nothing has ever run.

7. Add the mlops equivalent of
   `ansible/roles/rag_ingestion/tasks/compile_pipeline_version.yml` — build a venv,
   read the rendered pipeline-source ConfigMap, run `python pipeline.py <agent>`,
   apply the resulting `pipeline-kubernetes.yaml`.
8. **Reconcile the names.** `pipeline.py.tpl:104` compiles a DAG named
   `mlops-<agent>` while `templates/pipeline.yaml` renders exactly one CR named
   `mlops`. rag-ingestion renders a per-target CR alongside the base one — mirror
   that, or compile under the base name. Pick one and make both sides agree.
9. Fix `ansible/roles/mlops/tasks/install.yml:109`, which asserts
   `display_name == 'mlops'` against a CR whose displayName is
   `MLOps: dataset-to-model LoRA/PEFT pipeline` — it can never pass and is
   swallowed by its own `rescue`.
10. Re-enable `make d2 check mlops`: `ansible/playbooks/day2_check.yml:40-42`
    strips `mlops` from the component list, commented "no precheck.yml yet",
    but `ansible/roles/mlops/tasks/precheck.yml` exists and is 40 lines.

### Part C — serving (`gitops/charts/models/`)

11. Two new models, each needing its own file set (this chart is per-model by
    design — see `s3-serving-credentials.yaml`'s own comment on why the SA is not
    shared):

    | Model | `servedModelName` | ISVC name | Slice | Node |
    |---|---|---|---|---|
    | variant | `qwen3.5-9b-wesh` | `qwen35-9b-wesh` | `mig-2g.48gb` | `ip-10-18-67-65` |
    | base | `qwen3.5-9b` | `qwen35-9b` | `mig-1g.24gb` | `ip-10-18-15-25` |

    Per model: `llminferenceservice-<m>.yaml` (copy the **nested-values** shape of
    `llminferenceservice-gptoss.yaml`), `s3-serving-credentials-<m>.yaml`
    (ExternalSecret on Vault `rag/s3` with the `serving.kserve.io/s3-*`
    annotations, plus the `<name>-s3` ServiceAccount, sync-wave `-5`),
    `networkpolicy-<m>.yaml`, a values block, and a `maas.models[]` entry.
12. **The NetworkPolicy must admit `maas-default-gateway`** alongside ai-gateway
    and rag-service on TCP 8000. Omitting that rule produces a 504 *after* auth,
    subscription and rate-limit all pass — the failure mode
    `networkpolicy-gptoss.yaml` documents. Note `check_workload_hardening.py`
    only asserts that the chart renders ≥1 NetworkPolicy, so it will **not** catch
    a missing per-model one.
13. Reuse `_llmisvc-route.tpl` unchanged (it is already parameterized), and repeat
    the `--served-model-name` triple exactly as the two existing templates do —
    vLLM's argparse keeps only the last occurrence of the flag.
14. Set the base model's `--max-model-len` below the 32768 the 48 GB models use:
    19.3 GB of weights plus ~1 GB of KV at full context leaves little headroom in
    a 24 GB slice. Pair it with a high `--gpu-memory-utilization`.
15. Keep `spreadAcrossGpuNodes`' soft anti-affinity exactly as it is. Do **not**
    convert any term to `required` — that would contradict ADR-0351 decision 1 and
    WP-086's explicit design.

### Part D — routing, telemetry, OKF

16. `platform/ai-gateway/provider-routing.yaml` — four `kind: local` entries, each
    `-maas` immediately before its direct twin: `local-wesh-maas`, `local-wesh`,
    `local-qwen35-maas`, `local-qwen35`. All four need
    `eligible_for: [C1, C2, C3]` — Comage's `compare-historical-deals` computes at
    **C3**, where only local providers survive. Do **not** set `serves_adapters`.
17. `policies/model-routing/model-routing-policy.yaml` — because a preference is
    keyed by `(agent, task)` and an entry without `task` is rejected
    (`model_routing_policy.py:121`), "default for all of Comage's tasks" means
    **four new entries**: `check-deal-status`, `check-my-drive-and-mail`,
    `update-opportunity-status`, and the existing `compare-historical-deals`
    amended. Tekos: insert the variant in **second** position across its four
    entries — `answer-technical-question`, `find-relevant-docs` and
    `check-my-drive-docs` use the `preferred:`/`fallback:` shape;
    **`write-code` must keep `prefer:` with `mistral-codestral` at index 0 and
    stay non-strict**, or `evaluations/tekos/gate_checks.py:97-103` fails in CI.
18. `components/ai-gateway/app/telemetry.py:81-92` — add a `_COST_PER_SECOND_LOCAL`
    row for **each** of the four provider names. A `kind: local` entry with no row
    silently meters at $0.
19. Regenerate all **eight** OKF authorization-matrix blocks with
    `python3 platform/okf/generate_authorization_matrix.py`. They are generated
    between `BEGIN/END GENERATED AUTHORIZATION MATRIX` markers and byte-compared
    in CI; adding a provider changes the resolved chain for every agent, not just
    the two being re-routed. Never hand-edit them.

### Part E — the register-conformance evaluation

20. Add one handler to the shared `HANDLERS` dict in
    `evaluations/tekos/run_scenarios.py` (all six agents consume that one dict, so
    a single addition covers them). It sends the held-out `test.jsonl` prompts and
    scores register conformance — marker rate against the corpus README's rule 2/9
    vocabulary, with rule 11-13's "never slangify technical terminology, code,
    YAML, JSON, SQL or shell" asserted as a negative check.
21. Add the matching scenario entries for Comage, and wire the result into
    `mlops.py`'s `evaluate` stage so the run fails if **either** half fails. The
    existing acceptance gate stays untouched and must stay green — today it is
    entirely tone-blind (status codes, JSON fields, non-emptiness, latency, SSE
    framing; no semantic judge anywhere), so it is the substance half by
    construction, not by modification.

### Part F — statuses and index

22. ADR-0526 `Proposed` → `Implemented` (with the index row kept normalized-equal);
    `wp-34-lora-mlops.md`'s `State` line pointing here as the replacement of its
    objective — **never a rewrite of its body**; a new
    `## Phase 20: French urban-register model variant (added 2026-08-27, outside
    the original 40-ADR scope)` section plus tracker row in
    `docs/roadmap/implementation-roadmap.md`; the v0.4 paragraph in
    `docs/roadmap/versions.md`; a dated `MEMORY.md` bullet.

## What NOT to touch

- The **Decision text** of any existing ADR. ADR-0301/0302 are superseded in part
  by their `**Status:**` lines only — that is the sole legal body edit.
- `evaluations/*/scenarios.yaml` existing entries, and the acceptance gate's
  threshold or security checks. Part E **adds**, it does not relax.
- `gitops/charts/models/values.yaml`'s `loraAdapters` (stays `[]`), the
  `serves_adapters` flag, and `policies/model-routing/model-routing-policy.yaml`'s
  `adapters:` list — ADR-0303's mechanism is bypassed, not removed.
- The MIG `ResourceQuota` and `gitops/charts/machines`. This WP fits in the
  remaining slices exactly; if it does not, stop and ask rather than raising them.
- `spreadAcrossGpuNodes`' soft terms (see item 15).

## Acceptance checks (run from repo root; all must pass)

- `python3 -m pytest components/mlops/ -q` (and `python3 components/mlops/tests/test_mlops.py`)
- `helm lint gitops/charts/models` and `helm lint gitops/charts/mlops`
- `helm template gitops/charts/models` renders both new `LLMInferenceService`
  objects, each with its own NetworkPolicy and `maas.models[]`-derived manifests
- `python3 platform/okf/generate_authorization_matrix.py --check --all`
- `python3 evaluations/tekos/gate_checks.py`
- `python3 platform/security/check_workload_hardening.py`
- `python3 platform/supply-chain/check_build_matrix.py`
- `ansible-playbook ansible/playbooks/day2_{build,install,check}.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. `make d2 build mlops`, then compile and upload the `PipelineVersion` (Part B)
   and launch a run. The burst node scales 0→1 on the `nvidia.com/gpu` request.
2. Confirm the run: corpus → train → merge → both gate halves → registry, with a
   registered version whose artifact URI is the merged checkpoint.
3. Review and merge the promotion PR (ADR-0302 decision 7 — the pipeline never
   writes `models/values.yaml`), sync, and confirm both models `Ready` on
   **different** nodes with their own ids on `/v1/models`.
4. Verify routing live: a Comage turn answered in register by the variant, and
   the documented fallback when the variant is made unavailable; a Tekos turn
   answered by its first choice, and by the variant when that first choice is not.

## Status updates (then re-run check_docs.py)

- After the repo work merges: ADR-0526 → `Repo work merged`, index row to match;
  this brief's `State` likewise; tracker row `Operator pending`.
- After the live run and promotion: ADR-0526 → `Implemented`; index row
  `Implemented`; tracker → `Done`; `MEMORY.md` dated bullet.

## Out of scope / deferred

- Dynamic per-request adapter selection (WP-39 / ADR-0303) — bypassed here, still open.
- Extending `evaluations/benchmark.py --check-policy` (ADR-0305) to cover
  `preferences:` entries, not just `adapters:`. As it stands, a routing change
  that names a model rather than an adapter passes that CI gate without a
  benchmark artifact. Record the gap even if it is not closed here.
- Re-quantizing a merged checkpoint (the capability that would have made
  `qwen3.6-27b-instruct` or `gpt-oss-20b` viable bases — ADR-0526 Alternatives).
- Restoring ADR-0351 decision 5's single-node survivability, which needs capacity.
