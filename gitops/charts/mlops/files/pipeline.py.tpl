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
    # ADR-0538/WP-116. A key absent from this map never reaches the step
    # pod, so tracking would silently no-op. MLFLOW_WORKSPACE is explicit
    # rather than defaulted to the pod namespace: the KFP steps run in
    # zuno-mlops today, but WP-119 moves training into a TrainJob pod
    # whose namespace should not silently change where runs are recorded.
    "MLFLOW_TRACKING_URI": "MLFLOW_TRACKING_URI",
    "MLFLOW_WORKSPACE": "MLFLOW_WORKSPACE",
    "MODEL_REGISTRY_NAMESPACE": "MODEL_REGISTRY_NAMESPACE",
    "MODEL_REGISTRY_URL": "MODEL_REGISTRY_URL",
    # ADR-0526 (WP-087). A key absent from this map is NOT a compile
    # error - it simply never reaches the pod, and the stage falls back to
    # mlops.py's own default. That is why every new ConfigMap key must be
    # added here too.
    "MLOPS_MODELS_S3_REGION": "MLOPS_MODELS_S3_REGION",
    "MLOPS_MODELS_S3_ENDPOINT": "MLOPS_MODELS_S3_ENDPOINT",
    "MLOPS_MERGED_MODEL_S3URI": "MLOPS_MERGED_MODEL_S3URI",
    "MLOPS_MERGED_OVERWRITE": "MLOPS_MERGED_OVERWRITE",
    "KEYCLOAK_URL": "KEYCLOAK_URL",
    "FRONTEND_URL": "FRONTEND_URL",
}
GATE_SECRET = "{{ .Values.acceptanceGate.credentialsSecretName }}"
GATE_CA_CONFIGMAP = "{{ .Values.acceptanceGate.caConfigMapName }}"
AGENT_CONFIG_KEYS = {
    "MLOPS_AGENT": "MLOPS_AGENT",
    "MLOPS_KNOWLEDGE_DOMAINS": "MLOPS_KNOWLEDGE_DOMAINS",
    "MLOPS_BASE_MODEL": "MLOPS_BASE_MODEL",
    "MLOPS_LORA_R": "MLOPS_LORA_R",
    "MLOPS_LORA_ALPHA": "MLOPS_LORA_ALPHA",
    "MLOPS_LORA_DROPOUT": "MLOPS_LORA_DROPOUT",
    "MLOPS_STYLE_CORPUS_S3URI": "MLOPS_STYLE_CORPUS_S3URI",
    "MLOPS_LORA_TARGET_MODULES": "MLOPS_LORA_TARGET_MODULES",
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
    # WP-087: the `evaluate` stage authenticates a demo persona against
    # Keycloak (evaluations/tekos/run_scenarios.py raises outright without
    # this) and needs THE TARGET AGENT'S frontend client secret for the
    # token exchange. The env var name is derived from the agent -
    # run_scenarios.py reads f"{AGENT.upper()}_FRONTEND_CLIENT_SECRET" -
    # so a hardcoded TEKOS_ name left a comage run raising
    # "COMAGE_FRONTEND_CLIENT_SECRET is required to obtain persona
    # tokens" on 11 of its 22 scenarios and on all 6 security checks.
    # Applied to every stage rather than just evaluate - the stages share
    # one configure() contract, and an env var an earlier stage ignores
    # costs nothing.
    kubernetes.use_secret_as_env(
        task,
        secret_name=GATE_SECRET,
        secret_key_to_env={
            "demo-persona-password": "DEMO_PERSONA_PASSWORD",
            f"{agent}-frontend-client-secret": f"{agent.upper()}_FRONTEND_CLIENT_SECRET",
        },
    )
    # The platform's internal root CA, mirrored into this namespace by
    # ansible/roles/mlops/tasks/install.yml. Not a secret - a public
    # certificate - so it travels as a ConfigMap. Without it the gate's
    # HTTPS calls to Keycloak and the agent frontends fail
    # CERTIFICATE_VERIFY_FAILED and the ADR-0028 rate counts each as an
    # agent failure. mlops.py's _install_internal_ca() folds it into
    # certifi's bundle before running the gate.
    kubernetes.use_config_map_as_env(
        task,
        config_map_name=GATE_CA_CONFIGMAP,
        config_map_key_to_env={"ca.crt": "ZUNO_INTERNAL_CA_PEM"},
    )
    kubernetes.set_image_pull_policy(task, "{{ .Values.images.mlops.pullPolicy }}")
    return task


prepare_dataset = component("prepare-dataset")
train_lora = component("train-lora")
merge_export = component("merge-export")
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
    # ADR-0526 (WP-087) decision 1: merge the adapter into a standalone
    # checkpoint BEFORE evaluate, so push-registry can register the merged
    # artifact's URI rather than the adapter's. No GPU here - but see
    # values.yaml's merge: block for why it still needs explicit cpu,
    # memory and ephemeral-storage: ~19GB in, ~19GB out, on a pod that
    # would otherwise be BestEffort and evictable mid-upload.
    merged = configure(merge_export(run_id=run_id).after(trained), agent="{{ $name }}")
    merged.set_cpu_request("{{ $root.Values.merge.resources.cpuRequest }}")
    merged.set_cpu_limit("{{ $root.Values.merge.resources.cpuLimit }}")
    merged.set_memory_request("{{ $root.Values.merge.resources.memoryRequest }}")
    merged.set_memory_limit("{{ $root.Values.merge.resources.memoryLimit }}")
    # NO ephemeral-storage request: kfp 2.17's PipelineTask simply has no
    # setter for it (only cpu, memory and accelerator), and kfp.kubernetes
    # offers volumes rather than resource requests. Verified against the
    # installed SDK rather than assumed - an earlier revision of this file
    # called set_ephemeral_storage_request and every compile died on
    # AttributeError.
    #
    # That leaves a real exposure, because this stage genuinely needs the
    # disk: ~19GB of base checkpoint in, ~19GB of merged checkpoint out, on
    # the same filesystem. With no request it is a zero-request pod, which
    # this cluster has already shown means "scheduled onto the fullest node
    # and evicted first" - that is exactly how the mlops IMAGE build failed
    # three times before being pinned. So steer it the only way the SDK
    # allows, to the node group that actually has the headroom (155GB and
    # 182GB free versus 19-47GB elsewhere).
    #
    # Not the gpu-burst node the training stage uses: that one scales from
    # zero and is reclaimed after training, and parking a 40GB merge on it
    # would hold an expensive node alive for no GPU work. These are the
    # permanent MIG nodes, whose nvidia.com/gpu taint is PreferNoSchedule -
    # it deprioritises without blocking, and this task requests no GPU.
    kubernetes.add_node_selector(
        merged,
        label_key="{{ $root.Values.merge.nodeSelector.key }}",
        label_value="{{ $root.Values.merge.nodeSelector.value }}",
    )
    evaluated = configure(evaluate(run_id=run_id).after(merged), agent="{{ $name }}")
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
            # ALWAYS suffixed by target. PipelineVersion names are unique
            # per NAMESPACE, not per pipeline - rag-ingestion proved this
            # live on 2026-08-21, where compiling a second domain produced
            # an object literally named the chart's single version value
            # and was rejected "Pipeline spec is immutable". mlops has no
            # privileged first target to leave unsuffixed, so every one is
            # suffixed and there is no special case to get wrong later.
            pipeline_version_name="{{ .Values.pipeline.version }}-" + target,
            namespace="{{ .Values.platform.namespace }}",
            include_pipeline_manifest=False,
        ),
    )
