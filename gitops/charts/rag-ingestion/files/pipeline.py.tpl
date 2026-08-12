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

# REDHAT_SOURCES_JSON/CONFLUENCE_SOURCES_JSON carry the full redhat[]/
# confluence[] arrays (one product+version pair / one tech x skill-tier
# source per entry, including confluence[].requiredGroups for
# acl_groups tagging) - flat REDHAT_*/CONFLUENCE_* keys can't represent
# multiple sources, only a single ConfigMap-env mapping.
CONFIG_KEYS = {
    "REDHAT_SOURCES_JSON": "REDHAT_SOURCES_JSON",
    "CONFLUENCE_SOURCES_JSON": "CONFLUENCE_SOURCES_JSON",
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
    "CORPUS_INCREMENTAL": "CORPUS_INCREMENTAL",
    "CORPUS_HASH_ALGORITHM": "CORPUS_HASH_ALGORITHM",
    "CORPUS_DELETE_ORPHANS": "CORPUS_DELETE_ORPHANS",
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


def configure(task, *, confluence=False, postgres=False, embedding=False):
    kubernetes.use_config_map_as_env(task, config_map_name=CONFIGMAP, config_map_key_to_env=CONFIG_KEYS)
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
            secret_name=PG_SECRET,
            secret_key_to_env={"PGUSER": "PGUSER", "PGPASSWORD": "PGPASSWORD"},
        )
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
detect_changes = component("detect-changes")
normalize = component("normalize")
chunk = component("chunk")
embed = component("embed")
index_pgvector = component("index-pgvector")
validate = component("validate")


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


if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=rag_ingestion_pipeline,
        package_path="pipeline-kubernetes.yaml",
        kubernetes_manifest_format=True,
        kubernetes_manifest_options=KubernetesManifestOptions(
            pipeline_name="{{ .Values.pipeline.name }}",
            pipeline_version_name="{{ .Values.pipeline.version }}",
            namespace="{{ .Values.platform.namespace }}",
            include_pipeline_manifest=False,
        ),
    )
