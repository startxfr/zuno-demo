# WP-06/ADR-0322 full config.yaml for OGXServer.spec.overrideConfig.
#
# Two real, upstream bugs made the two earlier CR-driven modes unusable:
#
# 1. spec.distribution (name/image) - the OGX operator's own OCI-manifest-
#    fetch client is anonymous-only by design (github.com/ogx-ai/
#    ogx-k8s-operator pkg/config/oci_fetcher.go's own doc comment) and never
#    performs the WWW-Authenticate challenge/token exchange real registries
#    require. Ruled out live, in order: registry.redhat.io (401), our own
#    zuno-ai-build mirror (400, no Authorization header sent at all), and a
#    real public docker.io/ogxai/distribution-starter image (401 - Docker
#    Hub enforces the OAuth challenge even for public images, which this
#    client never follows). spec.baseConfig ("takes precedence over OCI
#    label resolution") sidesteps this - the CRD's own documented mechanism.
#
# 2. spec.providers (typed CR fields) - pkg/config/provider.go's
#    expandPgvectorProvider() never sets a `persistence` key on the
#    generated remote::pgvector provider config, for any input (confirmed
#    by reading the function - it has no persistence-related code path at
#    all), and the CRD's own PgvectorProvider type has no field to supply
#    one either. The server crashes hard on startup:
#    `self.kvstore = await kvstore_impl(self.config.persistence)` with
#    persistence=None -> AttributeError. Not something any CR field can
#    work around - genuinely missing from the typed-provider pipeline.
#
# Fix: spec.overrideConfig ("a full config.yaml override... mutually
# exclusive with providers, resources, storage, disabledAPIs, and
# baseConfig") - full manual control, so the pgvector provider's
# `persistence` block (present in every OTHER provider example in the real
# upstream distribution-starter config this file is trimmed from) can
# actually be set. Content below: the real distribution-starter config.yaml
# (decoded from that same image's OCI labels, fetched live via one properly
# authenticated request outside the operator), trimmed to the two real
# providers this deployment needs (zuno-vllm, zuno-pgvector - the "starter"
# distro's other 20-odd placeholder cloud/vector providers removed, they
# were never going to be used), with real Helm-templated connection values
# in place of the upstream template's ${env.*} placeholders.
# registered_resources.models emptied - the upstream defaults referenced
# provider_id: all, meaningless once only one inference provider exists.
# The pgvector password is injected as a real env var by
# spec.workload.overrides.env (ogxserver.yaml) from the same
# ogx-pgvector-password Secret the typed-provider path already used.
version: 2
distro_name: starter
apis:
- batches
- file_processors
- files
- inference
- interactions
- messages
- responses
- skills
- tool_runtime
- vector_io
providers:
  inference:
  - provider_id: zuno-vllm
    provider_type: remote::vllm
    config:
      base_url: {{ .Values.ogxServer.vllmEndpoint }}
      max_tokens: 4096
      api_token: fake
  vector_io:
  - provider_id: zuno-pgvector
    provider_type: remote::pgvector
    config:
      host: {{ .Values.ogxServer.pgvector.host }}
      port: {{ .Values.ogxServer.pgvector.port }}
      db: {{ .Values.ogxServer.pgvector.database }}
      user: {{ .Values.ogxServer.pgvector.user }}
      password: ${env.PGVECTOR_PASSWORD:=}
      distance_metric: COSINE
      vector_index:
        type: HNSW
        m: 16
        ef_construction: 64
        ef_search: 40
      persistence:
        namespace: vector_io::pgvector
        backend: kv_default
  files:
  - provider_id: builtin-files
    provider_type: inline::localfs
    config:
      storage_dir: ${env.FILES_STORAGE_DIR:=~/.ogx/distributions/starter/files}
      metadata_store:
        table_name: files_metadata
        backend: sql_default
  file_processors:
  - provider_id: auto
    provider_type: inline::auto
  interactions:
  - provider_id: builtin
    provider_type: inline::builtin
    config:
      store:
        table_name: interactions
        backend: sql_default
  messages:
  - provider_id: builtin
    provider_type: inline::builtin
    config:
      kvstore:
        namespace: message_batches
        backend: kv_default
  responses:
  - provider_id: builtin
    provider_type: inline::builtin
    config:
      persistence:
        responses:
          table_name: responses
          backend: sql_default
          max_write_queue_size: 10000
          num_writers: 4
      memory_config:
        default_vector_store_provider_id: zuno-pgvector
  skills:
  - provider_id: builtin
    provider_type: inline::builtin
    config:
      persistence:
        namespace: skills
        backend: kv_default
  tool_runtime:
  - provider_id: file-search
    provider_type: inline::file-search
  batches:
  - provider_id: reference
    provider_type: inline::reference
    config:
      sqlstore:
        table_name: batches
        backend: sql_default
storage:
  backends:
    kv_default:
      type: kv_sqlite
      db_path: ${env.SQLITE_STORE_DIR:=~/.ogx/distributions/starter}/kvstore.db
    sql_default:
      type: sql_sqlite
      db_path: ${env.SQLITE_STORE_DIR:=~/.ogx/distributions/starter}/sql_store.db
  stores:
    metadata:
      namespace: registry
      backend: kv_default
    inference:
      table_name: inference_store
      backend: sql_default
      max_write_queue_size: 10000
      num_writers: 4
    conversations:
      table_name: openai_conversations
      backend: sql_default
    prompts:
      table_name: prompts
      backend: sql_default
    connectors:
      table_name: connectors
      backend: sql_default
registered_resources:
  models: []
  vector_stores: []
server:
  port: 8321
vector_stores:
  default_provider_id: zuno-pgvector
  # default_embedding_model/default_reranker_model deliberately omitted:
  # validated only `if not None` (ogx/core/stack.py's
  # validate_vector_stores_config) against registered_resources.models,
  # which this override leaves empty - WP-06's corpus-proof/provider-
  # parity scope tests vector_io directly with pre-computed embeddings
  # (matching rag-service's own pattern), not OGX's file-search/embed-at-
  # rest convenience layer. Setting either without a matching model
  # registration crashes startup (confirmed live: "Reranker model
  # '.../Qwen3-Reranker-0.6B' not found. Available reranker models: []").
  file_search_params:
    header_template: 'file_search tool found {num_chunks} chunks:

      BEGIN of file_search tool results.

      '
    footer_template: 'END of file_search tool results.

      '
  context_prompt_params:
    chunk_annotation_template: 'Result {index}

      Content: {chunk.content}

      Metadata: {metadata}

      '
    context_template: 'The above results were retrieved to help answer the user''s
      query: "{query}". Use them as supporting information only in answering this
      query. {annotation_instruction}

      '
  annotation_prompt_params:
    enable_annotations: true
    annotation_instruction_template: Cite sources immediately at the end of sentences
      before punctuation, using `<|file-id|>` format like 'This is a fact <|file-Cn3MSNn72ENTiiq11Qda4A|>.'.
      Do not add extra punctuation. Use only the file IDs provided, do not invent
      new ones.
    chunk_annotation_template: '[{index}] {metadata_text} cite as <|{file_id}|>

      {chunk_text}

      '
  file_ingestion_params:
    default_chunk_size_tokens: 512
    default_chunk_overlap_tokens: 128
  chunk_retrieval_params:
    chunk_multiplier: 5
    max_tokens_in_context: 4000
    default_reranker_strategy: rrf
    rrf_impact_factor: 60.0
    weighted_search_alpha: 0.5
    default_search_mode: vector
  file_batch_params:
    max_concurrent_files_per_batch: 3
    file_batch_chunk_size: 10
    cleanup_interval_seconds: 86400
  contextual_retrieval_params:
    default_timeout_seconds: 120
    default_max_concurrency: 3
    max_document_tokens: 100000
connectors: []
