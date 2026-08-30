import sys

from kfp import compiler, dsl, kubernetes
from kfp.compiler.compiler_utils import KubernetesManifestOptions

IMAGE = "{{ include "rag-ingestion.image" . }}"
CONFIGMAP = "{{ include "rag-ingestion.fullname" . }}-config"
S3_SECRET = "{{ .Values.s3.secretName }}"
PG_SECRET = "{{ .Values.postgres.secretName }}"
{{- $confluenceEnabled := gt (len .Values.confluence) 0 }}
{{- if $confluenceEnabled }}
CONFLUENCE_SECRET = "{{ (first .Values.confluence).authentication.secretName }}"
{{- end }}
EMBEDDING_SECRET = "{{ .Values.embedding.auth.secretName }}"

# ADR-0204 part 2 (WP-22): every pipeline pod reads one env contract; the
# per-domain ConfigMaps (templates/domain-configmaps.yaml) carry the same
# key set as tech's (templates/configmap.yaml) with domain-specific
# values - INGESTION_DOMAIN is what the CLI's fetch-stage guard checks.
# REDHAT_SOURCES_JSON/CONFLUENCE_SOURCES_JSON etc. carry full arrays as
# JSON blobs - flat keys can't represent multiple sources.
CONFIG_KEYS = {
    "INGESTION_DOMAIN": "INGESTION_DOMAIN",
    "REDHAT_SOURCES_JSON": "REDHAT_SOURCES_JSON",
    "CONFLUENCE_SOURCES_JSON": "CONFLUENCE_SOURCES_JSON",
    "SALESFORCE_SOURCES_JSON": "SALESFORCE_SOURCES_JSON",
    "SXA_DUMP_SCHEMA_S3_KEY": "SXA_DUMP_SCHEMA_S3_KEY",
    "SXA_DUMP_DATA_S3_KEY": "SXA_DUMP_DATA_S3_KEY",
    "SXA_SNAPSHOT_ID": "SXA_SNAPSHOT_ID",
    "SXA_S3_ENDPOINT": "SXA_S3_ENDPOINT",
    "SXA_S3_BUCKET": "SXA_S3_BUCKET",
    "SXA_S3_REGION": "SXA_S3_REGION",
    "SXA_S3_PATH_STYLE": "SXA_S3_PATH_STYLE",
    "S3_ENDPOINT": "S3_ENDPOINT",
    "S3_BUCKET": "S3_BUCKET",
    "S3_REGION": "S3_REGION",
    "S3_PATH_STYLE": "S3_PATH_STYLE",
    "S3_RAW_PREFIX": "S3_RAW_PREFIX",
    "S3_NORMALIZED_PREFIX": "S3_NORMALIZED_PREFIX",
    "S3_MANIFEST_PREFIX": "S3_MANIFEST_PREFIX",
    "S3_FAILED_PREFIX": "S3_FAILED_PREFIX",
    "PGHOST": "PGHOST",
    "PGPORT": "PGPORT",
    "PGDATABASE": "PGDATABASE",
    "PGSCHEMA": "PGSCHEMA",
    "PGSSLMODE": "PGSSLMODE",
    "EMBEDDING_ENDPOINT": "EMBEDDING_ENDPOINT",
    "EMBEDDING_MODEL": "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS": "EMBEDDING_DIMENSIONS",
    "EMBEDDING_BATCH_SIZE": "EMBEDDING_BATCH_SIZE",
    "CHUNKING_STRATEGY": "CHUNKING_STRATEGY",
    "CHUNK_MAX_TOKENS": "CHUNK_MAX_TOKENS",
    "CHUNK_OVERLAP_TOKENS": "CHUNK_OVERLAP_TOKENS",
    "CHUNK_PRESERVE_CODE_BLOCKS": "CHUNK_PRESERVE_CODE_BLOCKS",
    "CHUNK_PRESERVE_TABLES": "CHUNK_PRESERVE_TABLES",
    "CORPUS_INCREMENTAL": "CORPUS_INCREMENTAL",
    "CORPUS_HASH_ALGORITHM": "CORPUS_HASH_ALGORITHM",
    "CORPUS_DELETE_ORPHANS": "CORPUS_DELETE_ORPHANS",
    # WP-24 freshness objective. This key existed in the config ConfigMap
    # since 0619a1f but was never forwarded here, so normalize silently
    # omitted stale_after from every chunk and validate fail-closed on the
    # whole corpus once rows actually indexed.
    "STALE_AFTER": "STALE_AFTER",
    # WP-57: fetch-stage concurrency knobs - must be present in every
    # domain's ConfigMap the same way every key above is (missing one
    # here is a CreateContainerConfigError at pod start, the exact
    # incident SXA_S3_ENDPOINT's own comment above documents).
    "FETCH_REDHAT_CONCURRENCY": "FETCH_REDHAT_CONCURRENCY",
    "FETCH_SXA_WRITE_CONCURRENCY": "FETCH_SXA_WRITE_CONCURRENCY",
    # WP-58: detect-changes' per-document S3 read pool - same
    # every-domain-ConfigMap requirement as the two keys above.
    "DETECT_CHANGES_READ_CONCURRENCY": "DETECT_CHANGES_READ_CONCURRENCY",
    "VALIDATE_READ_CONCURRENCY": "VALIDATE_READ_CONCURRENCY",
    # ADR-0219: normalize/chunk/embed/index-pgvector worker pools - same
    # every-domain-ConfigMap requirement as the keys above.
    "NORMALIZE_CONCURRENCY": "NORMALIZE_CONCURRENCY",
    "CHUNK_CONCURRENCY": "CHUNK_CONCURRENCY",
    "EMBED_CONCURRENCY": "EMBED_CONCURRENCY",
    "INDEX_READ_CONCURRENCY": "INDEX_READ_CONCURRENCY",
}

# Per-domain wiring (rendered from values.yaml's domains map): which
# ConfigMap, which database credential Secret and which source-system
# credential Secret each domain's tasks mount. "tech" is the chart's
# top-level config.
CONFIGMAPS = {
    "tech": CONFIGMAP,
{{- range $name, $domain := .Values.domains }}
{{- if $domain.enabled }}
    "{{ $name }}": "{{ include "rag-ingestion.fullname" $ }}-config-{{ $name }}",
{{- end }}
{{- end }}
}
PG_SECRETS = {
    "tech": PG_SECRET,
{{- range $name, $domain := .Values.domains }}
{{- if $domain.enabled }}
    "{{ $name }}": "{{ $domain.postgres.secretName }}",
{{- end }}
{{- end }}
}
SOURCE_SECRETS = {
{{- range $name, $domain := .Values.domains }}
{{- if and $domain.enabled $domain.salesforce }}
    "{{ $name }}": (
        "{{ $domain.salesforce.secretName }}",
        {"SALESFORCE_INSTANCE_URL": "SALESFORCE_INSTANCE_URL", "SALESFORCE_TOKEN": "SALESFORCE_TOKEN"},
    ),
{{- end }}
{{- end }}
}

# load-sxa-dump needs its own S3 credentials, for the dedicated SXA bucket
# rather than the shared corpus one. Kept as a separate, additive map (a
# list per domain) rather than folded into SOURCE_SECRETS above, which
# carries at most one secret per domain. ADR-0219 removed the second entry
# that used to sit here, the MariaDB import target's password.
SXA_SOURCE_SECRETS = {
{{- range $name, $domain := .Values.domains }}
{{- if and $domain.enabled $domain.sxaDump }}
    "{{ $name }}": [
        (
            "{{ $domain.sxaDump.s3.secretName }}",
            {"SXA_AWS_ACCESS_KEY_ID": "SXA_AWS_ACCESS_KEY_ID", "SXA_AWS_SECRET_ACCESS_KEY": "SXA_AWS_SECRET_ACCESS_KEY"},
        ),
    ],
{{- end }}
{{- end }}
}


# WP-067 live verification (2026-08-26) found every stage below ran with
# no cpu/memory request or limit at all - values.yaml's resources: block
# existed for some stages but nothing here ever read it (dead config).
# KFP has no bulk/toYaml-style resources setter, so configure() below
# applies each of the four set_*_request/set_*_limit calls per task,
# keyed by stage name.
RESOURCES = {
    "fetch-redhat": {"requests": {{ .Values.resources.fetch.requests | toJson }}, "limits": {{ .Values.resources.fetch.limits | toJson }}},
    "fetch-confluence": {"requests": {{ .Values.resources.fetch.requests | toJson }}, "limits": {{ .Values.resources.fetch.limits | toJson }}},
    "fetch-salesforce": {"requests": {{ .Values.resources.fetch.requests | toJson }}, "limits": {{ .Values.resources.fetch.limits | toJson }}},
    "load-sxa-dump": {"requests": {{ .Values.resources.fetch.requests | toJson }}, "limits": {{ .Values.resources.fetch.limits | toJson }}},
    "detect-changes": {"requests": {{ .Values.resources.detectChanges.requests | toJson }}, "limits": {{ .Values.resources.detectChanges.limits | toJson }}},
    "normalize": {"requests": {{ .Values.resources.normalize.requests | toJson }}, "limits": {{ .Values.resources.normalize.limits | toJson }}},
    "chunk": {"requests": {{ .Values.resources.chunk.requests | toJson }}, "limits": {{ .Values.resources.chunk.limits | toJson }}},
    "embed": {"requests": {{ .Values.resources.embed.requests | toJson }}, "limits": {{ .Values.resources.embed.limits | toJson }}},
    "index-pgvector": {"requests": {{ .Values.resources.index.requests | toJson }}, "limits": {{ .Values.resources.index.limits | toJson }}},
    "validate": {"requests": {{ .Values.resources.validate.requests | toJson }}, "limits": {{ .Values.resources.validate.limits | toJson }}},
    "reconcile-acls": {"requests": {{ .Values.resources.reconcileAcls.requests | toJson }}, "limits": {{ .Values.resources.reconcileAcls.limits | toJson }}},
}


def component(stage: str):
    @dsl.container_component
    def _component():
        return dsl.ContainerSpec(
            image=IMAGE,
            command=["/opt/app-root/src/rag-ingestion"],
            args=[stage],
        )
    return _component


def configure(task, *, stage, domain="tech", confluence=False, postgres=False, embedding=False, source_secret=False, fetch_stages=None):
    resources = RESOURCES[stage]
    task.set_cpu_request(resources["requests"]["cpu"])
    task.set_cpu_limit(resources["limits"]["cpu"])
    task.set_memory_request(resources["requests"]["memory"])
    task.set_memory_limit(resources["limits"]["memory"])
    kubernetes.use_config_map_as_env(task, config_map_name=CONFIGMAPS[domain], config_map_key_to_env=CONFIG_KEYS)
    kubernetes.use_secret_as_env(
        task,
        secret_name=S3_SECRET,
        secret_key_to_env={
            "AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY",
        },
    )
    if confluence:
        secret_map = {"CONFLUENCE_TOKEN": "CONFLUENCE_TOKEN"}
{{- if and $confluenceEnabled (eq (first .Values.confluence).authentication.type "api-token") }}
        secret_map["CONFLUENCE_USERNAME"] = "CONFLUENCE_USERNAME"
{{- end }}
        kubernetes.use_secret_as_env(task, secret_name=CONFLUENCE_SECRET, secret_key_to_env=secret_map)
    if postgres:
        kubernetes.use_secret_as_env(
            task,
            secret_name=PG_SECRETS[domain],
            secret_key_to_env={"PGUSER": "PGUSER", "PGPASSWORD": "PGPASSWORD"},
        )
    if source_secret and domain in SOURCE_SECRETS:
        secret_name, secret_map = SOURCE_SECRETS[domain]
        kubernetes.use_secret_as_env(task, secret_name=secret_name, secret_key_to_env=secret_map)
    if source_secret and domain in SXA_SOURCE_SECRETS:
        for secret_name, secret_map in SXA_SOURCE_SECRETS[domain]:
            kubernetes.use_secret_as_env(task, secret_name=secret_name, secret_key_to_env=secret_map)
{{- if .Values.embedding.auth.enabled }}
    if embedding:
        kubernetes.use_secret_as_env(
            task,
            secret_name=EMBEDDING_SECRET,
            secret_key_to_env={"EMBEDDING_API_TOKEN": "EMBEDDING_API_TOKEN"},
        )
{{- end }}
    if fetch_stages:
        # WP-100: scopes detect-changes' changeset key and orphan detection
        # to this run's own source(s) - set per task (not via the shared
        # ConfigMap) since knowledge.tech's two pipelines mount the SAME
        # ConfigMap but must carry different scopes.
        task.set_env_variable("INGESTION_FETCH_STAGES", ",".join(fetch_stages))
    kubernetes.set_image_pull_policy(task, "{{ .Values.images.ingestion.pullPolicy }}")
    return task


fetch_redhat = component("fetch-redhat")
fetch_confluence = component("fetch-confluence")
fetch_salesforce = component("fetch-salesforce")
load_sxa_dump = component("load-sxa-dump")
detect_changes = component("detect-changes")
normalize = component("normalize")
chunk = component("chunk")
embed = component("embed")
index_pgvector = component("index-pgvector")
validate = component("validate")
reconcile_acls = component("reconcile-acls")

FETCH_COMPONENTS = {
    "fetch-redhat": fetch_redhat,
    "fetch-confluence": fetch_confluence,
    "fetch-salesforce": fetch_salesforce,
    "load-sxa-dump": load_sxa_dump,
}


{{- /* WP-100 (ADR-0105 amendment): knowledge.tech's two sources
(fetch-redhat, fetch-confluence) each get their own independently
schedulable pipeline instead of one shared "rag_ingestion_pipeline" -
same generic per-source-with-fetchStages shape as the domains loop below,
but domain="tech" is fixed so both reuse CONFIGMAPS["tech"]/
PG_SECRETS["tech"] (the same ConfigMap/Postgres secret, keeping both
sources in the one knowledge.tech database per ADR-0202). fetch_stages is
threaded into every stage so detect-changes/normalize/.../validate scope
their shared-S3-state access to just this pipeline's source(s) (see
_changeset_key/_run_scope_source_types in rag_ingestion.py). */}}
{{- range $srcName, $src := .Values.techSources }}
@dsl.pipeline(
    name="{{ $.Values.pipeline.name }}-tech-{{ $srcName }}",
    description="knowledge.tech ({{ $srcName }}) ingestion - {{ $.Values.pipeline.description }}",
)
def rag_ingestion_pipeline_tech_{{ $srcName | replace "-" "_" }}():
    fetch_stages = {{ $src.fetchStages | toJson }}
    fetches = []
{{- range $stage := $src.fetchStages }}
    fetches.append(configure(
        FETCH_COMPONENTS["{{ $stage }}"](), stage="{{ $stage }}", domain="tech",
{{- if eq $stage "fetch-confluence" }} confluence=True,{{- end }}
        fetch_stages=fetch_stages,
    ))
{{- end }}
    changes = configure(detect_changes().after(*fetches), stage="detect-changes", domain="tech", fetch_stages=fetch_stages)
    normalized = configure(normalize().after(changes), stage="normalize", domain="tech", fetch_stages=fetch_stages)
    chunks = configure(chunk().after(normalized), stage="chunk", domain="tech", fetch_stages=fetch_stages)
    embeddings = configure(embed().after(chunks), stage="embed", domain="tech", embedding=True, fetch_stages=fetch_stages)
    indexed = configure(index_pgvector().after(embeddings), stage="index-pgvector", domain="tech", postgres=True, fetch_stages=fetch_stages)
    validated = configure(validate().after(indexed), stage="validate", domain="tech", postgres=True, fetch_stages=fetch_stages)
{{- if $src.reconcileAcls }}
    # ADR-0110 (WP-25): only the source with live Confluence access runs
    # this - a no-op on the redhat-only pipeline would just mount
    # Confluence credentials for nothing (see stage_reconcile_acls).
    configure(reconcile_acls().after(validated), stage="reconcile-acls", domain="tech", confluence=True, postgres=True)
{{- end }}


{{- end }}
{{- range $name, $domain := .Values.domains }}
{{- if $domain.enabled }}


@dsl.pipeline(
    name="{{ $.Values.pipeline.name }}-{{ $name }}",
    description="knowledge.{{ $name }} ingestion - {{ $.Values.pipeline.description }}",
)
def rag_ingestion_pipeline_{{ $name | replace "-" "_" }}():
    fetches = []
{{- range $stage := $domain.fetchStages }}
    fetches.append(configure(FETCH_COMPONENTS["{{ $stage }}"](), stage="{{ $stage }}", domain="{{ $name }}", source_secret=True))
{{- end }}
    changes = configure(detect_changes().after(*fetches), stage="detect-changes", domain="{{ $name }}")
    normalized = configure(normalize().after(changes), stage="normalize", domain="{{ $name }}")
    chunks = configure(chunk().after(normalized), stage="chunk", domain="{{ $name }}")
    embeddings = configure(embed().after(chunks), stage="embed", domain="{{ $name }}", embedding=True)
    indexed = configure(index_pgvector().after(embeddings), stage="index-pgvector", domain="{{ $name }}", postgres=True)
    validated = configure(validate().after(indexed), stage="validate", domain="{{ $name }}", postgres=True)
    # ADR-0110 (WP-25): a no-op for every domain but knowledge.tech (none
    # of these fetchStages is fetch-confluence today) - wired uniformly
    # so a future domain that DOES gain a confluence source doesn't need
    # a template change to get reconciliation for free.
    configure(reconcile_acls().after(validated), stage="reconcile-acls", domain="{{ $name }}", postgres=True)
{{- end }}
{{- end }}


PIPELINES = {
{{- range $srcName, $src := .Values.techSources }}
    "tech-{{ $srcName }}": (rag_ingestion_pipeline_tech_{{ $srcName | replace "-" "_" }}, "{{ $.Values.pipeline.name }}-tech-{{ $srcName }}"),
{{- end }}
{{- range $name, $domain := .Values.domains }}
{{- if $domain.enabled }}
    "{{ $name }}": (rag_ingestion_pipeline_{{ $name | replace "-" "_" }}, "{{ $.Values.pipeline.name }}-{{ $name }}"),
{{- end }}
{{- end }}
}


if __name__ == "__main__":
    # One compile per pipeline: `python pipeline.py [tech-redhat|tech-confluence|sales|sxa-legacy]`
    # (default tech-redhat).
    target = sys.argv[1] if len(sys.argv) > 1 else "tech-redhat"
    pipeline_func, pipeline_name = PIPELINES[target]
    # PipelineVersion is a plain namespaced Kubernetes resource - its
    # metadata.name is unique per (namespace, kind), NOT scoped per
    # pipeline (spec.pipelineName doesn't disambiguate it). A single
    # chart-wide "{{ .Values.pipeline.version }}" name here collided the
    # moment a second domain's PipelineVersion was ever applied (confirmed
    # live 2026-08-21: sxa's compile got rejected with "Pipeline spec is
    # immutable" against tech's already-existing v0-3-0 object) - every
    # pipeline's version name must be suffixed to stay unique, including
    # WP-100's two tech-<source> pipelines (there is no more single "tech"
    # exempt from this rule).
    _pipeline_version_name = "{{ .Values.pipeline.version }}-" + target
    compiler.Compiler().compile(
        pipeline_func=pipeline_func,
        package_path="pipeline-kubernetes.yaml",
        kubernetes_manifest_format=True,
        kubernetes_manifest_options=KubernetesManifestOptions(
            pipeline_name=pipeline_name,
            pipeline_version_name=_pipeline_version_name,
            namespace="{{ .Values.platform.namespace }}",
            include_pipeline_manifest=False,
        ),
    )
