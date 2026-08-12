-- Zuno Demo - RAG retrieval fixture corpus (ADR-0046)
--
-- Fictional/synthetic technical documentation for the Tekos agent's demo
-- corpus - not real Red Hat documentation, invented for this demo (same
-- non-nominative-data spirit as data/sxa/fixtures/seed.sql, ADR-0025).
-- Deliberately includes conflicting per-version guidance, a bilingual
-- (EN/FR) pair, a classification/ACL-restricted internal document and a
-- stale document, per ADR-0046's Operational consideration ("Add test
-- corpora containing conflicting versions and bilingual content").
--
-- Run after data/sxa/schema/002_pgvector.sql, data/rag/schema/003_rag_metadata.sql
-- and data/rag/schema/004_rag_chunking.sql against a database with the
-- `document_embeddings` table already created.
-- No `embedding` values are set (NULL) - no live embedding model is
-- reachable in the environment this fixture was authored in; hybrid
-- search still serves these rows via full-text search alone (see
-- components/rag-service/README.md's "Degradation" note) until a real
-- ingestion pipeline backfills embeddings (ADR-0105, v1).

INSERT INTO document_embeddings (source, title, content, metadata) VALUES

-- Conflicting per-version GPU sizing guidance - the exact scenario
-- ADR-0046's Context calls out ("Similarity alone can return an incorrect
-- OpenShift version even when the user names a version").
(
    'https://docs.example.internal/openshift-ai/3.5/gpu-sizing',
    'OpenShift AI 3.5 - GPU sizing for vLLM ServingRuntimes',
    'On OpenShift AI 3.5, size a vLLM ServingRuntime for a 7B-parameter model on a single NVIDIA L4 (24GB): reserve roughly 2GB for CUDA/runtime overhead, leaving about 22GB for weights plus KV cache. FP16 weights for a 7B model need approximately 14GB, leaving headroom for a moderate KV cache at typical context lengths. For larger 13B-34B models, prefer an L40S (48GB) or multi-GPU tensor parallelism.',
    '{"product": "openshift-ai", "version": "3.5", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-06-01", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/openshift-ai/2.16/gpu-sizing',
    'OpenShift AI 2.16 - GPU sizing for vLLM ServingRuntimes',
    'On OpenShift AI 2.16, the vLLM ServingRuntime template defaults assumed a T4 (16GB) or A10 (24GB) baseline. A 7B-parameter model in FP16 (about 14GB of weights) left very little headroom for KV cache on a T4 - an A10 or larger was recommended for anything beyond short-context single-request serving. The 3.5 release changed the recommended baseline GPU and default memory headroom formula - see the 3.5 sizing guide, do not apply these 2.16 numbers to a 3.5 deployment.',
    '{"product": "openshift-ai", "version": "2.16", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2025-02-10", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/openshift-ai/3.5/gpu-sizing-fr',
    'OpenShift AI 3.5 - dimensionnement GPU pour les ServingRuntimes vLLM',
    'Sur OpenShift AI 3.5, pour dimensionner un ServingRuntime vLLM pour un modele de 7 milliards de parametres sur un seul GPU NVIDIA L4 (24 Go) : reservez environ 2 Go pour la surcharge CUDA/runtime, ce qui laisse environ 22 Go pour les poids et le cache KV. Les poids en FP16 pour un modele de 7B necessitent environ 14 Go. Pour des modeles plus grands (13B a 34B), preferez un L40S (48 Go) ou du parallelisme tensoriel multi-GPU.',
    '{"product": "openshift-ai", "version": "3.5", "language": "fr", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-06-01", "provenance": "zuno-demo-fixture"}'::jsonb
),

-- Same product/version-conflict pattern for a second topic (ServingRuntime
-- configuration), so the version filter is exercised on more than one doc
-- pair.
(
    'https://docs.example.internal/openshift-ai/3.5/servingruntime-config',
    'OpenShift AI 3.5 - configuring a KServe ServingRuntime for vLLM',
    'OpenShift AI 3.5 ships a vLLM ClusterServingRuntime with a supportedModelFormats entry for vLLM and a containers[].args list accepting --max-model-len and --gpu-memory-utilization. InferenceServices reference it via spec.predictor.model.runtime. The 3.5 runtime image defaults gpu-memory-utilization to 0.90.',
    '{"product": "openshift-ai", "version": "3.5", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-05-20", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/openshift-ai/2.16/servingruntime-config',
    'OpenShift AI 2.16 - configuring a KServe ServingRuntime for vLLM',
    'OpenShift AI 2.16''s vLLM ServingRuntime predates the supportedModelFormats naming used from 3.0 onward and instead keys off spec.supportedModelFormats[].name = "vLLM" with a lowercase runtime label. InferenceServices on 2.16 commonly referenced the runtime by name directly rather than through spec.predictor.model.runtime. Do not copy 2.16 ServingRuntime YAML onto a 3.5 cluster without reconciling these field differences.',
    '{"product": "openshift-ai", "version": "2.16", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2024-11-05", "provenance": "zuno-demo-fixture"}'::jsonb
),

-- OpenShift platform docs (not OpenShift AI) - product dimension varies
-- independently of version, so a "product" filter alone (no version
-- named) still needs to work.
(
    'https://docs.example.internal/openshift/4.20/restricted-scc',
    'OpenShift 4.20 - the restricted-v2 SCC and Pod Security Admission',
    'OpenShift 4.20''s restricted-v2 SCC requires runAsNonRoot, drops ALL Linux capabilities, forbids privilege escalation and enforces RuntimeDefault seccomp. It assigns an arbitrary UID from the namespace''s allocated range rather than a fixed runAsUser - workloads must not hardcode one.',
    '{"product": "openshift", "version": "4.20", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-03-01", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/openshift/4.20/restricted-scc-fr',
    'OpenShift 4.20 - le SCC restricted-v2 et Pod Security Admission',
    'Le SCC restricted-v2 d''OpenShift 4.20 exige runAsNonRoot, supprime toutes les capacites Linux, interdit l''escalade de privileges et impose le profil seccomp RuntimeDefault. Il attribue un UID arbitraire depuis la plage allouee a l''espace de noms plutot qu''un runAsUser fixe.',
    '{"product": "openshift", "version": "4.20", "language": "fr", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-03-01", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/openshift/4.20/networkpolicy-guide',
    'OpenShift 4.20 - NetworkPolicy and OVN-Kubernetes ingress groups',
    'NetworkPolicy objects in OpenShift 4.20 (OVN-Kubernetes CNI) are additive: when multiple NetworkPolicies select the same pod, their allowed-ingress rules are unioned, never intersected. A namespace-wide "allow same namespace" policy therefore cannot be narrowed by a second, stricter policy on the same pod - design precise per-workload policies instead when isolation must be exact.',
    '{"product": "openshift", "version": "4.20", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-04-12", "provenance": "zuno-demo-fixture"}'::jsonb
),

-- Internal, classification/ACL-restricted document - proves retrieval
-- enforces ADR-0046's Security consideration ("Retrieval must never
-- return documents the user cannot access").
(
    'https://confluence.example.internal/wiki/spaces/TECH/pages/900001',
    'OpenShift AI 3.6 EA roadmap notes (internal, pre-release)',
    'Pre-release, internal-only notes on OpenShift AI 3.6 EA scope: expanded MaaS policy routing, a revised default GPU memory headroom formula, and KServe ServingRuntime v2 field names. Not for external distribution before GA.',
    '{"product": "openshift-ai", "version": "3.6", "language": "en", "source_type": "confluence", "classification": "C2", "acl_groups": ["consultant", "board"], "last_modified": "2026-07-15", "provenance": "confluence-internal-fixture"}'::jsonb
),

-- Stale document - exercises the freshness/stale_after metadata field.
(
    'https://docs.example.internal/openshift-ai/3.3/migration-notes',
    'OpenShift AI 3.3 migration notes (superseded)',
    'Migration notes for upgrading to OpenShift AI 3.3 from 3.2. Superseded by later release notes; retained only for historical reference.',
    '{"product": "openshift-ai", "version": "3.3", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2024-09-01", "stale_after": "2025-01-01", "provenance": "zuno-demo-fixture"}'::jsonb
),

-- No version tag at all - proves an unversioned doc still surfaces when
-- no version filter is requested, and correctly isn't excluded by a
-- product-only filter.
(
    'https://docs.example.internal/openshift-ai/upgrade-path-overview',
    'OpenShift AI upgrade path overview (2.16 to 3.5)',
    'A high-level overview of the supported upgrade path from OpenShift AI 2.16 to 3.5, spanning the ServingRuntime field renames and the GPU sizing formula change covered in each version''s own sizing guide.',
    '{"product": "openshift-ai", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-05-25", "provenance": "zuno-demo-fixture"}'::jsonb
),

-- Unrelated products, to prove product filtering actually excludes
-- non-matching rows rather than merely re-ranking them.
(
    'https://docs.example.internal/ai-gateway/3.5/routing-guide',
    'AI Inference Gateway - classification-driven provider routing',
    'The AI Inference Gateway resolves a local vLLM model first, falling back through approved SaaS providers in the order declared by provider-routing.yaml, filtered to providers eligible for the request''s data classification (C1/C2/C3) and further filtered to local-only when X-Zuno-Local-Only is set.',
    '{"product": "ai-gateway", "version": "3.5", "language": "en", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-05-28", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/vault/runbook-external-secrets',
    'Vault + External Secrets Operator operational runbook',
    'Standard runbook for rotating a Vault-backed credential consumed via an ExternalSecret: update the value in Vault, wait for the refreshInterval or force a sync, verify the target Secret''s resourceVersion changed, then roll the consuming Deployment if it does not already re-read the mounted Secret at runtime.',
    '{"product": "openshift", "version": "4.20", "language": "en", "source_type": "runbook", "classification": "C1", "last_modified": "2026-02-14", "provenance": "zuno-demo-fixture"}'::jsonb
),
(
    'https://docs.example.internal/postgresql/pgvector-guide-fr',
    'PostgreSQL et pgvector - guide de recherche hybride',
    'pgvector ajoute un type de colonne vector et des operateurs de distance (cosinus, L2, produit scalaire) a PostgreSQL. Combine a la recherche plein texte native (tsvector/tsquery), il permet une recherche hybride : fusionner un classement par similarite vectorielle et un classement par pertinence textuelle, par exemple via la fusion de rang reciproque (RRF).',
    '{"product": "postgresql", "language": "fr", "source_type": "product-doc", "classification": "C1", "last_modified": "2026-01-20", "provenance": "zuno-demo-fixture"}'::jsonb
)

-- (source, chunk_index), not (source) alone: 004_rag_chunking.sql replaced
-- the source-only uniqueness with a compound one to support real chunked
-- ingestion. Every row here implicitly takes chunk_index's default (0),
-- so the conflict target still matches.
ON CONFLICT (source, chunk_index) DO NOTHING;
