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
    "ARAMIS_SOURCES_JSON": "ARAMIS_SOURCES_JSON",
    "SXA_DUMP_S3_KEY": "SXA_DUMP_S3_KEY",
    "SXA_SNAPSHOT_ID": "SXA_SNAPSHOT_ID",
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
{{- if and $domain.enabled $domain.aramis }}
    "{{ $name }}": (
        "{{ $domain.aramis.secretName }}",
        {"ARAMIS_BASE_URL": "ARAMIS_BASE_URL", "ARAMIS_TOKEN": "ARAMIS_TOKEN"},
    ),
{{- end }}
{{- end }}
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


def configure(task, *, domain="tech", confluence=False, postgres=False, embedding=False, source_secret=False):
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
{{- if .Values.embedding.auth.enabled }}
    if embedding:
        kubernetes.use_secret_as_env(
            task,
            secret_name=EMBEDDING_SECRET,
            secret_key_to_env={"EMBEDDING_API_TOKEN": "EMBEDDING_API_TOKEN"},
        )
{{- end }}
    kubernetes.set_image_pull_policy(task, "{{ .Values.images.ingestion.pullPolicy }}")
    return task


fetch_redhat = component("fetch-redhat")
fetch_confluence = component("fetch-confluence")
fetch_salesforce = component("fetch-salesforce")
fetch_aramis = component("fetch-aramis")
load_sxa_dump = component("load-sxa-dump")
detect_changes = component("detect-changes")
normalize = component("normalize")
chunk = component("chunk")
embed = component("embed")
index_pgvector = component("index-pgvector")
validate = component("validate")

FETCH_COMPONENTS = {
    "fetch-redhat": fetch_redhat,
    "fetch-confluence": fetch_confluence,
    "fetch-salesforce": fetch_salesforce,
    "fetch-aramis": fetch_aramis,
    "load-sxa-dump": load_sxa_dump,
}


@dsl.pipeline(name="{{ .Values.pipeline.name }}", description="{{ .Values.pipeline.description }}")
def rag_ingestion_pipeline():
    rh = configure(fetch_redhat())
{{- if $confluenceEnabled }}
    cf = configure(fetch_confluence(), confluence=True)
    changes = configure(detect_changes().after(rh, cf))
{{- else }}
    changes = configure(detect_changes().after(rh))
{{- end }}
    normalized = configure(normalize().after(changes))
    chunks = configure(chunk().after(normalized))
    embeddings = configure(embed().after(chunks), embedding=True)
    indexed = configure(index_pgvector().after(embeddings), postgres=True)
    configure(validate().after(indexed), postgres=True)


{{- range $name, $domain := .Values.domains }}
{{- if $domain.enabled }}


@dsl.pipeline(
    name="{{ $.Values.pipeline.name }}-{{ $name }}",
    description="knowledge.{{ $name }} ingestion - {{ $.Values.pipeline.description }}",
)
def rag_ingestion_pipeline_{{ $name | replace "-" "_" }}():
    fetches = []
{{- range $stage := $domain.fetchStages }}
    fetches.append(configure(FETCH_COMPONENTS["{{ $stage }}"](), domain="{{ $name }}", source_secret=True))
{{- end }}
    changes = configure(detect_changes().after(*fetches), domain="{{ $name }}")
    normalized = configure(normalize().after(changes), domain="{{ $name }}")
    chunks = configure(chunk().after(normalized), domain="{{ $name }}")
    embeddings = configure(embed().after(chunks), domain="{{ $name }}", embedding=True)
    indexed = configure(index_pgvector().after(embeddings), domain="{{ $name }}", postgres=True)
    configure(validate().after(indexed), domain="{{ $name }}", postgres=True)
{{- end }}
{{- end }}


PIPELINES = {
    "tech": (rag_ingestion_pipeline, "{{ .Values.pipeline.name }}"),
{{- range $name, $domain := .Values.domains }}
{{- if $domain.enabled }}
    "{{ $name }}": (rag_ingestion_pipeline_{{ $name | replace "-" "_" }}, "{{ $.Values.pipeline.name }}-{{ $name }}"),
{{- end }}
{{- end }}
}


if __name__ == "__main__":
    # One compile per domain: `python pipeline.py [tech|sales|adv|sxa-legacy]`
    # (default tech, the original single-domain behavior).
    target = sys.argv[1] if len(sys.argv) > 1 else "tech"
    pipeline_func, pipeline_name = PIPELINES[target]
    compiler.Compiler().compile(
        pipeline_func=pipeline_func,
        package_path="pipeline-kubernetes.yaml",
        kubernetes_manifest_format=True,
        kubernetes_manifest_options=KubernetesManifestOptions(
            pipeline_name=pipeline_name,
            pipeline_version_name="{{ .Values.pipeline.version }}",
            namespace="{{ .Values.platform.namespace }}",
            include_pipeline_manifest=False,
        ),
    )
