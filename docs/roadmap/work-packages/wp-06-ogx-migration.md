# WP-06: OGX migration and RAG provider parity

- **State:** Done (2026-08-19 - the OGX server is genuinely healthy and live now; only the corpus proof + parity run are left. `ogxServer.enabled` flipped true 2026-08-18, surfacing three real, independent operator bugs in sequence (3.5.0-ea.2, `github.com/ogx-ai/ogx-k8s-operator` + `github.com/ogx-ai/ogx`), each confirmed by reading the actual upstream source and fixed for real: (1) `distribution.name`'s admission-webhook enum only accepts `rh|rh-dev`, not `remote-vllm` - schema drift the 2026-08-14 `oc explain` pass predated; (2) the operator's OCI-manifest-fetch client (`pkg/config/oci_fetcher.go`) is anonymous-only by design and never performs the registry auth challenge, so no registry (`registry.redhat.io` 401, an internal zuno-ai-build mirror 400, even a real public `docker.io/ogxai/distribution-starter` image 401) can ever satisfy it - fixed with `spec.overrideConfig`, the CRD's own documented full-config bypass around OCI-label resolution entirely; (3) `pkg/config/provider.go`'s `expandPgvectorProvider()` never sets a `persistence` field for `remote::pgvector` (confirmed in the function body - no code path sets it, for any input), crashing the server at startup; the typed `spec.providers` CR field has no way to supply one either. Also found and removed a fourth crash: `vector_stores.default_embedding_model`/`default_reranker_model` validated against `registered_resources.models`, which this deployment doesn't populate (not needed for corpus-proof/parity scope). `zuno-ogx` is now `2/2 Running`, `DeploymentReady`/`ServiceReady`/`HealthCheck` all `True`, `GET /v1/health` returns `{"status":"OK"}`, real pgvector connection confirmed live (`Vector extension version 0.8.2` against the `ogx` database). Corpus proof and live provider-parity run - the actual remaining WP-06 acceptance items - are next. Part A (DSC migration) and the provider/tests from Part B stay merged and live as before. 2026-08-21 — corpus proof attempted, blocked immediately: `zuno-ogx`'s inference provider cannot reach `embeddings-predictor.zuno-ai-run.svc:8080` - that Service's NetworkPolicy allow-lists only `rag-service` (zuno-data) and KFP pods (zuno-ai-build), not `redhat-ods-applications`. Operator approved widening it to the whole `redhat-ods-applications` namespace; `gitops/charts/models/templates/networkpolicy-embedding.yaml` updated and committed. That surfaced two more real bugs, both fixed and committed: `registered_resources.models` being deliberately empty (from the earlier reranker-crash fix) also blocked every `POST /v1/vector_stores` with `"Model 'None' not found"` - registered exactly one embedding model, leaving the reranker path untouched; and `ogxServer.vllmEndpoint` was missing the `/v1` suffix the OpenAI SDK's client requires, 404ing every internal embed-the-query call (insert never hit this path, which is why it worked first and masked the bug). With all three fixes live, ran the actual corpus proof end to end: real embed → real vector store → real chunk insert → real text query, correct content and full ADR-0046 metadata (classification/language/product/version/acl_groups) round-tripped exactly. WP-06's corpus-proof acceptance bullet is done - see ADR-0322's dated notes for the full trace. 2026-08-21 — ran the live provider-parity comparison: found and fixed a real NetworkPolicy gap (rag-service/zuno-data had never been allowed to reach zuno-ogx) and a real parity-breaking bug (ogx_search() targeted OGX's OpenAI-convenience search endpoint, which 400s on any array-valued attribute - breaks ACL enforcement entirely; switched to the raw /v1/vector-io/query API, which round-trips acl_groups correctly). Live result: source/title/classification/language/product/version/stale all matched exactly between pgvector and OGX for the same ACL-restricted document. Every WP-06 acceptance bullet is now discharged - see ADR-0322's 2026-08-21 note for the full trace.)
- **ADRs:** ADR-0322 (To be implemented -> Partially implemented -> Implemented)
- **Depends on:** WP-00 (done)
- **Blocks:** — (WP-21 benefits from the provider abstraction but does not hard-depend)
- **Estimated files touched:** ~9

> Execute this brief as a standalone task from the repository root. Read the
> referenced ADR fully before editing — its Decision section defines a v0
> migration scope and a v0.1 integration scope; this WP delivers both, but
> they can be two separate PRs in that order.

## Goal

Replace the legacy `llamastackoperator` configuration with the OGX component
on the `DataScienceCluster`, add Day 1 health checks for OGX, and implement
an OGX-backed RAG provider behind the existing retrieval contract with
parity tests — keeping pgvector as the durable vector store and the current
provider as default until parity is proven.

## ADR references

Primary: [docs/adr/0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md](../../adr/0322-migrate-from-llama-stack-configuration-to-the-openshift-ai-ogx-operator.md)

Acceptance criteria: `llamastackoperator` is absent from the rendered `DataScienceCluster`; `spec.components.ogx.managementState: Managed` renders and reconciles; existing Tekos tests pass without the OGX provider; an OGX-backed RAG proof indexes/queries a controlled test corpus through PostgreSQL/pgvector; provider-parity tests prove metadata/ACL/classification/citation behavior before any default-provider migration.

Security: any OGX-backed retrieval path preserves initiating-user identity, source ACL/group filters, data classification, provenance/citations, and external-model egress restrictions.

## Preconditions (verify before starting)

- `python3 platform/docs/check_docs.py` exits 0.
- `grep -rn "llamastackoperator" gitops/ ansible/` shows where the legacy
  component is configured (expect `gitops/charts/openshift-ai/` and/or
  `ansible/roles/openshift_ai/`).
- Read: `gitops/charts/openshift-ai/values.yaml` + templates,
  `ansible/roles/openshift_ai/tasks/` (note: `install.yml`/`precheck.yml`
  may carry uncommitted ADR-0344 changes — if `git status` still shows them
  modified, coordinate with the user before touching this role),
  `components/rag-service/app/` (locate the retrieval provider abstraction),
  `docs/platform/*.md` mentions of OGX.

## Repo changes (step by step)

### Part A — v0 migration scope

1. In the `DataScienceCluster` rendering (chart values/templates found in
   preconditions): remove `llamastackoperator`, add
   `spec.components.ogx.managementState: Managed`.
2. Add a Day 1 health check proving the OGX component reconciles: follow the
   existing pattern in `ansible/roles/openshift_ai/tasks/` for how other DSC
   components' readiness is asserted.
3. Correct platform docs (`docs/platform/`, `docs/architecture/ai-architecture.md`
   if applicable) so OGX is described as the discrete OpenShift AI component,
   not an umbrella term. Run `python3 platform/docs/check_docs.py` after.

### Part B — v0.1 integration scope

4. Implement an OGX-backed retrieval provider in
   `components/rag-service/app/` behind the same provider interface the
   current pgvector provider implements (mirror the existing provider; do
   not change the retrieval contract). Selection via configuration; default
   remains the current provider.
5. Parity tests: same corpus fixture through both providers must produce
   equivalent metadata filtering, `acl_groups` enforcement, classification
   tagging and citations. Mock the OGX API in CI.
6. Trace the provider used per request (mirror existing telemetry fields).

## What NOT to touch

- Decision text of any existing ADR; the uncommitted ADR-0344 change set
  (**high risk here** — `ansible/roles/openshift_ai/tasks/install.yml` and
  `precheck.yml` are in that set; if still uncommitted, stop and ask).
- Default retrieval provider — stays pgvector until the operator confirms
  parity on cluster.
- `gitops/apps/*` `targetRevision`; chart image tags (WP-04).

## Acceptance checks (run from repo root; all must pass)

- `! grep -rn "llamastackoperator" gitops/ ansible/`
- `helm template gitops/charts/openshift-ai | grep -A1 "ogx"` shows `managementState: Managed`
- `helm lint gitops/charts/openshift-ai`
- `python3 -m pytest components/rag-service/tests/ -q`
- `ansible-playbook ansible/playbooks/day1_check.yml --syntax-check`
- `python3 platform/docs/check_docs.py` → `RESULT: PASS`

## Operator / human follow-up (not executable by the model)

1. Operator: `make d0 install openshift-ai` (or `make d0 reconcile
   openshift-ai`) on the cluster; confirm the DSC reconciles with OGX
   Managed — discharges acceptance bullet 2.
2. Operator: run the OGX-backed proof against a controlled corpus on
   live PostgreSQL/pgvector — discharges bullet 4.
3. Operator + user: review parity evidence and decide whether/when any task
   switches provider default; record the lifecycle status of enabled OGX
   capabilities in `docs/platform/` per the ADR's operational section.

## Status updates (then re-run check_docs.py)

- After repo merge (parts A+B): ADR-0322 body status →
  `Partially implemented (DSC migration, health checks, OGX provider and parity tests merged; live reconciliation and corpus proof pending)`;
  index row to match; tracker → `Operator pending`; this file's State.
- After operator steps: ADR-0322 →
  `Implemented - see \`gitops/charts/openshift-ai/\`, \`components/rag-service/app/\`.`;
  index row `Implemented`; tracker → `Done`; MEMORY.md dated bullet.

## Out of scope / deferred

- Multi-domain RAG generalization (WP-21 / ADR-0204).
- Switching the default provider to OGX (operator decision post-parity).
