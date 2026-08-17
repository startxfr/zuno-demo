import sys

from kfp import compiler, dsl, kubernetes
from kfp.compiler.compiler_utils import KubernetesManifestOptions

IMAGE = "{{ include "mlops.image" . }}"
BASE_CONFIGMAP = "{{ include "mlops.fullname" . }}-config"
S3_SECRET = "{{ .Values.s3.secretName }}"
PG_SECRET = "{{ .Values.postgres.secretName }}"

# One ConfigMap per enabled candidate agent
# (templates/agent-configmaps.yaml) - MLOPS_AGENT and its training
# parameters are baked in per agent, the same "one env contract per
# run-target" pattern rag-ingestion's own per-domain ConfigMaps use
# (files/pipeline.py.tpl there is this file's direct template).
AGENT_CONFIGMAPS = {
{{- range $name, $agent := .Values.agents }}
{{- if $agent.enabled }}
    "{{ $name }}": "{{ include "mlops.fullname" $ }}-config-{{ $name }}",
{{- end }}
{{- end }}
}

BASE_CONFIG_KEYS = {
    "S3_ENDPOINT": "S3_ENDPOINT",
    "S3_BUCKET": "S3_BUCKET",
    "S3_REGION": "S3_REGION",
    "S3_PATH_STYLE": "S3_PATH_STYLE",
    "S3_DATASET_PREFIX": "S3_DATASET_PREFIX",
    "S3_MODEL_PREFIX": "S3_MODEL_PREFIX",
    "S3_EVAL_PREFIX": "S3_EVAL_PREFIX",
    "S3_REGISTRY_PREFIX": "S3_REGISTRY_PREFIX",
    "PGHOST": "PGHOST",
    "PGPORT": "PGPORT",
    "PGDATABASE": "PGDATABASE",
    "PGSCHEMA": "PGSCHEMA",
    "PGSSLMODE": "PGSSLMODE",
    "MLOPS_EVALUATIONS_DIR": "MLOPS_EVALUATIONS_DIR",
    "MODEL_REGISTRY_NAMESPACE": "MODEL_REGISTRY_NAMESPACE",
    "MODEL_REGISTRY_URL": "MODEL_REGISTRY_URL",
}
AGENT_CONFIG_KEYS = {
    "MLOPS_AGENT": "MLOPS_AGENT",
    "MLOPS_KNOWLEDGE_DOMAINS": "MLOPS_KNOWLEDGE_DOMAINS",
    "MLOPS_BASE_MODEL": "MLOPS_BASE_MODEL",
    "MLOPS_LORA_R": "MLOPS_LORA_R",
    "MLOPS_LORA_ALPHA": "MLOPS_LORA_ALPHA",
    "MLOPS_LORA_DROPOUT": "MLOPS_LORA_DROPOUT",
}


def component(stage: str):
    """Every stage shares one image and one CLI contract
    (components/mlops/src/mlops.py's own STAGES) - run_id is the only
    genuinely per-run input, passed as a CLI argument (a dsl.PipelineParam
    substituted at run submission time) rather than an env var, since
    ConfigMaps are baked in per agent at chart-render time, not per run.
    """
    @dsl.container_component
    def _component(run_id: str):
        return dsl.ContainerSpec(
            image=IMAGE,
            command=["/opt/app-root/src/mlops-run"],
            args=[stage, "--run-id", run_id],
        )
    return _component


def configure(task, *, agent):
    kubernetes.use_config_map_as_env(task, config_map_name=BASE_CONFIGMAP, config_map_key_to_env=BASE_CONFIG_KEYS)
    kubernetes.use_config_map_as_env(
        task, config_map_name=AGENT_CONFIGMAPS[agent], config_map_key_to_env=AGENT_CONFIG_KEYS
    )
    kubernetes.use_secret_as_env(
        task,
        secret_name=S3_SECRET,
        secret_key_to_env={
            "AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY",
        },
    )
    kubernetes.use_secret_as_env(
        task,
        secret_name=PG_SECRET,
        secret_key_to_env={"PGUSER": "PGUSER", "PGPASSWORD": "PGPASSWORD"},
    )
    kubernetes.set_image_pull_policy(task, "{{ .Values.images.mlops.pullPolicy }}")
    return task


prepare_dataset = component("prepare-dataset")
train_lora = component("train-lora")
evaluate = component("evaluate")
push_registry = component("push-registry")

PIPELINES = {}

{{- $root := . }}
{{- range $name, $agent := .Values.agents }}
{{- if $agent.enabled }}


@dsl.pipeline(
    name="{{ $root.Values.pipeline.name }}-{{ $name }}",
    description="LoRA/PEFT adapter pipeline for {{ $name }} - {{ $root.Values.pipeline.description }}",
)
def mlops_pipeline_{{ $name | replace "-" "_" }}(run_id: str):
    dataset = configure(prepare_dataset(run_id=run_id), agent="{{ $name }}")
    trained = configure(train_lora(run_id=run_id).after(dataset), agent="{{ $name }}")
    # ADR-0351: train-lora is the only stage that needs a GPU. It requests
    # a whole nvidia.com/gpu, which only the scale-from-zero gpu-burst
    # MachineSet provides (the permanent inference node is MIG-partitioned
    # and advertises nvidia.com/mig-* only) - a run therefore triggers a
    # 0->1 node scale-up and the node is reclaimed ~10min after the stage
    # completes. The toleration matches the burst node's taint, which keeps
    # every non-training pod off it so scale-down is never blocked.
    trained.set_accelerator_type("{{ $root.Values.training.gpu.resource }}")
    trained.set_accelerator_limit("{{ $root.Values.training.gpu.count }}")
    trained.set_cpu_request("{{ $root.Values.training.resources.cpuRequest }}")
    trained.set_cpu_limit("{{ $root.Values.training.resources.cpuLimit }}")
    trained.set_memory_request("{{ $root.Values.training.resources.memoryRequest }}")
    trained.set_memory_limit("{{ $root.Values.training.resources.memoryLimit }}")
    kubernetes.add_node_selector(
        trained,
        label_key="{{ $root.Values.training.gpu.nodeSelector.key }}",
        label_value="{{ $root.Values.training.gpu.nodeSelector.value }}",
    )
    kubernetes.add_toleration(
        trained,
        key="{{ $root.Values.training.gpu.toleration.key }}",
        operator="Equal",
        value="{{ $root.Values.training.gpu.toleration.value }}",
        effect="{{ $root.Values.training.gpu.toleration.effect }}",
    )
    # ADR-0302 point 5: evaluate must run (and pass) before push-registry
    # is even attempted - .after() enforces the DAG ordering; evaluate's
    # own non-zero exit on a failing gate (components/mlops/src/mlops.py)
    # stops the pipeline here, before push-registry's task ever starts.
    evaluated = configure(evaluate(run_id=run_id).after(trained), agent="{{ $name }}")
    configure(push_registry(run_id=run_id).after(evaluated), agent="{{ $name }}")


PIPELINES["{{ $name }}"] = (mlops_pipeline_{{ $name | replace "-" "_" }}, "{{ $root.Values.pipeline.name }}-{{ $name }}")
{{- end }}
{{- end }}


if __name__ == "__main__":
    # One compile per candidate agent: `python pipeline.py <agent>`
    # (e.g. "comage" - see values.yaml's agents: map for what's enabled).
    if len(sys.argv) < 2 or sys.argv[1] not in PIPELINES:
        raise SystemExit(f"usage: python pipeline.py <agent> - one of {sorted(PIPELINES)}")
    target = sys.argv[1]
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
