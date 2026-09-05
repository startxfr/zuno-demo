# ADR-0302: Build dataset-to-model MLOps pipelines

- **Status:** Superseded in part by ADR-0526 for the dataset sourcing and training objective (decisions 2 and 4); the pipeline, storage, evaluation-gate, registry and human-reviewed-promotion rules (decisions 1, 3, 5-7) remain in effect and are now live-verified (WP-133, 2026-09-05): a full `tekos` KFP run (`prepare-dataset` → `train-lora` → `evaluate` PASS → `push-registry`) produced a genuine adapter-only Model Registry version (`wp126-20260904-201830`), promoted via a human-reviewed GitOps PR, and confirmed serving. Prior status for the record: Partially implemented - pipeline, roles and tests merged.
- **Target:** v0.3
- **Date:** 2026-08-12
- **Decision owners:** Zuno Demo architecture team

## Decision

Promote this decision from a one-line v0.3-roadmap entry
(`../roadmap/adr-decisions-v0.3.md`) to a full record, for the same reason as
ADR-0301: `ansible/roles/mlops` needs a real target to scaffold
against. This ADR is the pipeline that produces the LoRA/PEFT adapters
ADR-0301 serves - dataset preparation, training, evaluation, registry
push and deployment promotion, automated end to end. It reuses existing
platform conventions rather than introducing a second ingestion/
pipeline/registry stack:

1. **Pipeline mechanism** - a KFP pipeline running on the existing
   `DataSciencePipelinesApplication`/`aipipelines` OpenShift AI
   component, the same mechanism ADR-0330 already established for
   rag-ingestion. `ansible/roles/mlops` becomes the day1-run role that
   activates/schedules it (mirroring `ansible/roles/rag_ingestion`), and
   a new `ansible/roles/mlops_build` (mirroring `rag_ingestion_build`)
   builds the pipeline's container image via the same
   `ansible/tasks/apply_openshift_build.yml` task every other build
   component uses. Image source lives at `components/mlops/`, following
   the `components/<name>` (source) vs `gitops/charts/<name>`
   (manifests) split.
2. **Dataset preparation** - training examples are curated from two
   existing sources rather than a new collection mechanism: agent
   evaluation transcripts (`evaluations/<agent>/`, ADR-0027's 20
   acceptance scenarios plus real usage logs once an agent is active)
   and the RAG document store (`document_embeddings`, ADR-0015/0046)
   for domain-jargon grounding. No new data-collection surface is
   introduced by this ADR.
3. **Storage** - datasets and trained adapter artifacts round-trip
   through the same S3 bucket/credential convention ADR-0330's
   rag-ingestion pipeline already established (stage-to-S3 between KFP
   pod stages, since each stage runs in its own pod with no shared
   local disk) - not a new storage system.
4. **Training** - LoRA/PEFT fine-tuning (ADR-0301) of the target base
   model, parameterized by which agent/use case the run is for. First
   candidate: Comage domain-jargon adaptation, per ADR-0301.
5. **Evaluation gate before promotion** - a trained adapter must pass
   the same acceptance mechanism a base model change would: the target
   agent's existing 20-scenario suite (ADR-0027) at the existing 75%
   threshold (ADR-0028), run against the candidate adapter before it is
   eligible for promotion. This reuses `evaluations/<agent>/
   run_acceptance_gate.py` rather than inventing a parallel evaluation
   harness; it does not replace or lower that gate for the base model.
6. **Registry push** - a passing adapter is registered in the OpenShift
   AI Model Registry (`gitops/charts/openshift-ai/values.yaml`,
   `modelregistry.registriesNamespace: zuno-ai-build`), versioned, per
   ADR-0301's point 3.
7. **Deployment promotion is human-reviewed, not automatic** - a passing,
   registered adapter is promoted to serving by a GitOps PR updating
   `gitops/charts/models/values.yaml` (ADR-0301's static adapter
   reference), going through the normal repository review process
   (Standard clauses' Acceptance criteria) rather than the pipeline
   pushing directly to a serving deployment. This keeps a human decision
   point between "evaluation passed" and "serving live traffic."

Explicitly out of this ADR's scope: which adapter a request routes to
at runtime (ADR-0303/ADR-0304), and continuous automated benchmarking
across candidate models (ADR-0305) - this ADR only closes the
dataset-to-registered-artifact pipeline.

## Alternatives considered

- **Manual, ad hoc fine-tuning runs** (a data scientist running a
  one-off script outside GitOps/CI) - rejected: produces unversioned,
  unregistered artifacts this platform's supply-chain conventions
  (ADR-0115) explicitly avoid elsewhere, and skips the acceptance gate
  every other agent-facing change goes through.
- **A new, dedicated pipeline/orchestration system** - rejected: the
  platform already has a working KFP mechanism (ADR-0330) for exactly
  this shape of multi-stage, S3-round-tripping pipeline; standing up a
  second one would duplicate operational surface for no benefit.
- **Automatic promotion on evaluation pass** - rejected: removes the
  human review point the rest of this platform relies on for anything
  that changes what an agent serves to users.

## Security considerations

Training datasets drawn from `document_embeddings` inherit that data's
existing classification/`acl_groups` (ADR-0046); a dataset assembled
from C2/C3-tagged content produces a C2/C3-classified adapter per
ADR-0301's point 4 - this pipeline must not silently launder a
restricted source's classification down to C1 by omitting the tag
during dataset assembly. Evaluation-gate bypass (promoting an adapter
that failed the 75% threshold) must not be possible through this
pipeline's own tooling; only the standard repository review process
can override it, the same way a below-threshold base model change
would require an explicit ADR.

## Operational considerations

Pipeline run history, evaluation results and registry versions must be
inspectable the same way `rag-ingestion`'s KFP runs are (ADR-0330's
Operational considerations) - `make d1 check mlops` becomes meaningful
once this is implemented, rather than the current `mlops` precheck's
placeholder "contract registered... pending" message
(`ansible/roles/mlops/tasks/precheck.yml`).

## Evolution (2026-08-15)

Point 6's Model Registry reference used this Decision text's original
`zuno-ai-build` namespace assumption, written before ADR-0331's
reversion. The live `gitops/charts/openshift-ai/values.yaml`
(`modelregistry.registriesNamespace`) is `rhoai-model-registries`, RHOAI's
own true default - `components/mlops/`'s push-registry stage (WP-34)
reads this from the real Helm value via an env var
(`MODEL_REGISTRY_NAMESPACE`), never hardcoding either string, so this
correction needs no further ADR/code change to stay accurate.

See [Standard clauses](README.md#standard-clauses) for Context,
Consequences, Migration/evolution and Acceptance criteria.

## Related ADRs

- [ADR-0015](0015-use-postgresql-and-pgvector-as-the-persistent-data-platform.md) - Use PostgreSQL and pgvector as the persistent data platform
- [ADR-0027](0027-evaluate-every-agent-with-twenty-acceptance-scenarios.md) - Evaluate every agent with twenty acceptance scenarios
- [ADR-0028](0028-require-a-seventy-five-percent-evaluation-threshold.md) - Require a seventy-five percent evaluation threshold
- [ADR-0046](0046-make-rag-retrieval-metadata-aware-and-bilingual.md) - Make RAG retrieval metadata-aware and bilingual
- [ADR-0115](0115-use-immutable-and-verifiable-software-supply-chain-artifacts.md) - Use immutable and verifiable software supply chain artifacts
- [ADR-0056](0056-restructure-deployment-into-day-0-day-1-sequencing.md) - Restructure deployment into Day 0 / Day 1 sequencing (`mlops` run component)
- [ADR-0301](0301-introduce-lora-and-peft-model-customization.md) - Introduce LoRA and PEFT model customization (this pipeline's output)
- [ADR-0330](0330-integrate-the-rag-ingestion-pipeline-as-a-day1-component.md) - Integrate the rag-ingestion pipeline as a Day 1 component (the KFP/S3 pattern this ADR reuses)
