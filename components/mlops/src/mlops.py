#!/usr/bin/env python3
"""Runtime entrypoint for the MLOps LoRA/PEFT pipeline (ADR-0301/ADR-0302,
WP-34).

The command contract mirrors components/rag-ingestion's exactly, for the
same reason (see that module's own docstring): a single image serves
every KFP stage, and each stage round-trips its state through S3 - KFP
runs each stage in its own pod, so there is no shared local disk between
them:

    prepare-dataset -> <datasetPrefix>/<agent>/<run_id>/examples.jsonl + dataset_manifest.json
    train-lora      -> <modelPrefix>/<agent>/<run_id>/adapter/*        + train_manifest.json
    evaluate         -> <evalPrefix>/<agent>/<run_id>/gate_result.json
    push-registry    -> <registryPrefix>/<agent>/<run_id>/registration.json

ADR-0302 point 7 / this pipeline's own contract: this CLI never writes to
gitops/charts/models/values.yaml - promotion to serving is a
human-reviewed GitOps PR, always. push-registry only registers the
adapter artifact in the Model Registry; nothing in this file, or anywhere
else in the pipeline, touches the serving chart.

ADR-0302 point 2: no new data-collection surface. prepare-dataset draws
only from two already-existing sources: (a) `document_embeddings` rows
for the target agent's declared knowledge domain(s) - continued-
pretraining-style text examples, the direct mechanism behind "domain/
jargon adaptation" (ADR-0301 point 5), and (b) the target agent's own
evaluations/<agent>/scenarios.yaml chat-shaped scenario messages, a
stand-in for "real usage logs" (ADR-0302 point 2's second source) until
an agent has live traffic to draw from - this demo environment has none
yet, and this file says so rather than fabricating transcripts.

ADR-0302 point 5 / Security considerations: evaluate must run before
push-registry, and push-registry refuses to run against a missing or
failing gate result - there is no bypass path in this CLI, only the
standard repository review process (same as a below-threshold base-model
change would require).

ADR-0301 point 4 / ADR-0302 Security considerations: classification
propagates from source to adapter, never silently downgraded. Each
document_embeddings row's own metadata.classification contributes to the
dataset's effective classification via the same escalate-only rule
ADR-0034 already establishes for a live agent turn (see _escalate below);
the trained adapter inherits that as train_manifest.json's
"classification" field, carried through to the registry push.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
import psycopg
import requests
import yaml
from botocore.exceptions import ClientError

logger = logging.getLogger("mlops")

STAGES = (
    "prepare-dataset",
    "train-lora",
    "evaluate",
    "push-registry",
)

# ADR-0034's own escalation order, mirrored here (never re-derived from a
# different source of truth - see components/agent-runtime/app/graph/
# nodes.py's _escalate for the live-turn equivalent of this same rule).
_CLASSIFICATION_ORDER = {"C1": 1, "C2": 2, "C3": 3}


def _escalate(current: str, candidate: str) -> str:
    if _CLASSIFICATION_ORDER.get(candidate, 1) > _CLASSIFICATION_ORDER.get(current, 1):
        return candidate
    return current


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


def _env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"Missing required environment variable: {name}")
    return val


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


def _env_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    val = os.environ.get(name)
    if not val:
        return list(default or [])
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass
class MlopsConfig:
    # S3 (same shape as rag-ingestion's own CorpusStore config - one
    # bucket, prefix-per-pipeline-output rather than a bucket per output).
    s3_endpoint: Optional[str]
    s3_bucket: str
    s3_region: Optional[str]
    s3_path_style: bool
    aws_access_key_id: Optional[str]
    aws_secret_access_key: Optional[str]
    dataset_prefix: str
    model_prefix: str
    eval_prefix: str
    registry_prefix: str

    # Postgres (document_embeddings is rag-service's own table - mlops
    # only ever reads it, never writes, per ADR-0302 point 2).
    pg_host: str
    pg_port: int
    pg_database: str
    pg_schema: str
    pg_sslmode: str
    pg_user: Optional[str]
    pg_password: Optional[str]

    # Run identity.
    agent: str
    run_id: str
    knowledge_domains: List[str]

    # Dataset/training parameters.
    max_dataset_rows: int
    base_model: str
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    cpu_safe: bool  # forces a tiny, real-but-trivial training run (no GPU needed)

    # evaluations/<agent>/quality_gate.py integration.
    evaluations_dir: str

    # ADR-0301 point 3 / D5 (docs/adr/0301, 0302 dated progress notes):
    # the OpenShift AI Model Registry's real namespace
    # (gitops/charts/openshift-ai/values.yaml's
    # modelregistry.registriesNamespace) is rhoai-model-registries, not
    # zuno-ai-build as those two ADRs' original Decision text assumed -
    # read from the environment (populated from the real Helm value by
    # this component's own chart/ConfigMap) rather than hardcoding either
    # string here.
    model_registry_url: Optional[str]
    model_registry_namespace: str


def load_config() -> MlopsConfig:
    return MlopsConfig(
        s3_endpoint=_env("S3_ENDPOINT"),
        s3_bucket=_env("S3_BUCKET", required=True),
        s3_region=_env("S3_REGION"),
        s3_path_style=_env_bool("S3_PATH_STYLE", False),
        aws_access_key_id=_env("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("AWS_SECRET_ACCESS_KEY"),
        dataset_prefix=_env("S3_DATASET_PREFIX", "mlops/datasets"),
        model_prefix=_env("S3_MODEL_PREFIX", "mlops/models"),
        eval_prefix=_env("S3_EVAL_PREFIX", "mlops/evaluations"),
        registry_prefix=_env("S3_REGISTRY_PREFIX", "mlops/registrations"),
        pg_host=_env("PGHOST", required=True),
        pg_port=_env_int("PGPORT", 5432),
        pg_database=_env("PGDATABASE", required=True),
        pg_schema=os.environ.get("PGSCHEMA", "public"),
        pg_sslmode=os.environ.get("PGSSLMODE", "require"),
        pg_user=os.environ.get("PGUSER"),
        pg_password=os.environ.get("PGPASSWORD"),
        agent=_env("MLOPS_AGENT", required=True),
        run_id=_env("MLOPS_RUN_ID", required=True),
        knowledge_domains=_env_list("MLOPS_KNOWLEDGE_DOMAINS"),
        max_dataset_rows=_env_int("MLOPS_MAX_DATASET_ROWS", 500),
        base_model=_env("MLOPS_BASE_MODEL", "ibm-granite/granite-3.1-2b-instruct"),
        lora_r=_env_int("MLOPS_LORA_R", 8),
        lora_alpha=_env_int("MLOPS_LORA_ALPHA", 16),
        lora_dropout=float(_env("MLOPS_LORA_DROPOUT", "0.05")),
        cpu_safe=_env_bool("MLOPS_CPU_SAFE", False),
        evaluations_dir=_env("MLOPS_EVALUATIONS_DIR", "/opt/app-root/src/evaluations"),
        model_registry_url=_env("MODEL_REGISTRY_URL"),
        model_registry_namespace=_env("MODEL_REGISTRY_NAMESPACE", "rhoai-model-registries"),
    )


# --------------------------------------------------------------------------
# S3 state store - same four-method shape as components/rag-ingestion's
# own CorpusStore, plus put_bytes (adapter files are binary, not JSON).
# --------------------------------------------------------------------------


class ArtifactStore:
    def __init__(self, config: MlopsConfig):
        self._bucket = config.s3_bucket
        from botocore.config import Config as BotoClientConfig

        client_kwargs: dict = {
            "region_name": config.s3_region or None,
            "aws_access_key_id": config.aws_access_key_id,
            "aws_secret_access_key": config.aws_secret_access_key,
            "config": BotoClientConfig(s3={"addressing_style": "path" if config.s3_path_style else "auto"}),
        }
        if config.s3_endpoint:
            client_kwargs["endpoint_url"] = config.s3_endpoint
        self._client = boto3.client("s3", **client_kwargs)

    def put_json(self, key: str, obj: Any) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )

    def get_json(self, key: str) -> Any:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read())

    def put_text(self, key: str, text: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=text.encode("utf-8"), ContentType="text/plain")

    def get_bytes(self, key: str) -> Optional[bytes]:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return resp["Body"].read()

    def put_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def list_keys(self, prefix: str) -> List[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        keys: List[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def put_dir(self, prefix: str, local_dir: Path) -> List[str]:
        """Uploads every file under local_dir, preserving relative paths
        under prefix - used once by train-lora to publish an adapter's
        saved-checkpoint directory (adapter_config.json + weights)."""
        uploaded = []
        for path in sorted(local_dir.rglob("*")):
            if path.is_file():
                key = f"{prefix}/{path.relative_to(local_dir).as_posix()}"
                self.put_bytes(key, path.read_bytes())
                uploaded.append(key)
        return uploaded

    def download_prefix(self, bucket: str, prefix: str, local_dir: Path) -> int:
        """Downloads every object under s3://bucket/prefix/ into
        local_dir, preserving relative paths - train-lora's base-model
        fetch (ADR-0518). Takes an explicit bucket (the base model lives
        under the models/ prefix, addressed by a full s3:// URI in
        MLOPS_BASE_MODEL) but reuses this store's client/credentials.
        download_file streams to disk via boto3's managed transfer -
        never get_bytes: safetensors shards run ~5GB each and buffering
        one in memory would eat half the train pod's memory request."""
        prefix = prefix.rstrip("/") + "/"
        paginator = self._client.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(prefix):]
                if not rel:
                    continue
                target = local_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                self._client.download_file(bucket, obj["Key"], str(target))
                count += 1
        return count


def _resolve_base_model(config: MlopsConfig, store: ArtifactStore, workdir: Path) -> str:
    """Returns a from_pretrained-loadable reference for config.base_model:
    an s3://<bucket>/<prefix> URI (ADR-0518 - the staged-in-S3 base, same
    convention every served model follows) is downloaded under workdir
    and the local directory path returned; anything else (an HF repo id,
    a pre-mounted local path) passes through untouched."""
    if not config.base_model.startswith("s3://"):
        return config.base_model
    bucket, _, prefix = config.base_model[len("s3://"):].partition("/")
    if not bucket or not prefix:
        raise SystemExit(f"malformed s3:// base model URI: {config.base_model}")
    local_dir = workdir / "base-model"
    local_dir.mkdir(parents=True, exist_ok=True)
    count = store.download_prefix(bucket, prefix, local_dir)
    if count == 0 or not (local_dir / "config.json").exists():
        raise SystemExit(
            f"base model download from {config.base_model} yielded no usable "
            f"checkpoint ({count} objects, config.json "
            f"{'present' if (local_dir / 'config.json').exists() else 'missing'})"
        )
    return str(local_dir)


def _run_prefix(base_prefix: str, config: MlopsConfig) -> str:
    return f"{base_prefix}/{config.agent}/{config.run_id}"


# --------------------------------------------------------------------------
# prepare-dataset
# --------------------------------------------------------------------------


def _pg_connect(config: MlopsConfig):
    conninfo = (
        f"host={config.pg_host} port={config.pg_port} dbname={config.pg_database} "
        f"user={config.pg_user} password={config.pg_password} sslmode={config.pg_sslmode}"
    )
    conn = psycopg.connect(conninfo, autocommit=False)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {config.pg_schema}, public")
    return conn


def _fetch_domain_grounding_rows(config: MlopsConfig) -> List[Dict[str, Any]]:
    """Reads document_embeddings rows for the agent's declared knowledge
    domain(s) - the "domain/jargon grounding" half of ADR-0302 point 2.
    Never writes to this table; rag-ingestion (ADR-0330) remains its only
    writer."""
    if not config.knowledge_domains:
        logger.warning("MLOPS_KNOWLEDGE_DOMAINS is empty; dataset will have no domain-grounding rows")
        return []
    conn = _pg_connect(config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source, title, content, metadata "
                "FROM document_embeddings "
                "WHERE metadata->>'domain' = ANY(%s) "
                "ORDER BY updated_at DESC "
                "LIMIT %s",
                (config.knowledge_domains, config.max_dataset_rows),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{"source": r[0], "title": r[1], "content": r[2], "metadata": r[3] or {}} for r in rows]


def _load_scenario_seed_texts(config: MlopsConfig) -> List[str]:
    """The "real usage logs" stand-in (ADR-0302 point 2): the target
    agent's own chat-shaped acceptance scenarios (evaluations/<agent>/
    scenarios.yaml), which carry realistic user phrasing for this
    domain. Not real usage - this demo has none yet - and this function
    says so rather than fabricating transcripts."""
    scenarios_path = Path(config.evaluations_dir) / config.agent / "scenarios.yaml"
    if not scenarios_path.is_file():
        logger.warning("no scenarios.yaml found for agent %s at %s", config.agent, scenarios_path)
        return []
    data = yaml.safe_load(scenarios_path.read_text(encoding="utf-8")) or {}
    chat_types = {"chat_basic_qa", "chat_first_token_latency", "chat_streaming_sse", "chat_triggers_tool"}
    return [s["message"] for s in data.get("scenarios", []) if s.get("type") in chat_types and s.get("message")]


def stage_prepare_dataset(config: MlopsConfig, store: ArtifactStore) -> None:
    rows = _fetch_domain_grounding_rows(config)
    seed_texts = _load_scenario_seed_texts(config)

    dataset_classification = "C1"
    examples: List[Dict[str, Any]] = []
    for row in rows:
        dataset_classification = _escalate(dataset_classification, row["metadata"].get("classification", "C1"))
        # Continued-pretraining-style example: persona-flavored domain
        # text, not a fabricated instruction/response pair - the direct
        # mechanism behind "domain/jargon adaptation" (ADR-0301 point 5).
        examples.append({"text": f"[{row['title']}]\n{row['content']}", "source": row["source"]})

    for text in seed_texts:
        examples.append({"text": text, "source": "evaluations-scenario"})

    run_prefix = _run_prefix(config.dataset_prefix, config)
    lines = "\n".join(json.dumps(ex, ensure_ascii=False) for ex in examples)
    store.put_text(f"{run_prefix}/examples.jsonl", lines)

    manifest = {
        "agent": config.agent,
        "run_id": config.run_id,
        "knowledge_domains": config.knowledge_domains,
        "example_count": len(examples),
        "grounding_row_count": len(rows),
        "scenario_seed_count": len(seed_texts),
        "classification": dataset_classification,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.put_json(f"{run_prefix}/dataset_manifest.json", manifest)
    logger.info("prepare-dataset: wrote %d examples for %s/%s (classification %s)",
                len(examples), config.agent, config.run_id, dataset_classification)


# --------------------------------------------------------------------------
# train-lora
# --------------------------------------------------------------------------


def _load_dataset_manifest(config: MlopsConfig, store: ArtifactStore) -> Dict[str, Any]:
    manifest = store.get_json(f"{_run_prefix(config.dataset_prefix, config)}/dataset_manifest.json")
    if manifest is None:
        raise SystemExit(
            f"no dataset_manifest.json for {config.agent}/{config.run_id} - run prepare-dataset first"
        )
    return manifest


def _run_lora_training(
    config: MlopsConfig,
    examples: List[Dict[str, Any]],
    output_dir: Path,
    base_model_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Real PEFT/LoRA fine-tuning of config.base_model on `examples`
    (causal-LM text corpus), saved to output_dir via save_pretrained().
    torch/transformers/peft/datasets are imported lazily, here and only
    here, so every other stage - and this whole module's own unit tests -
    never need those (large, GPU-oriented) packages installed.

    config.cpu_safe forces a tiny, real (not mocked) training run: one
    epoch, a handful of steps, no GPU required - the "training code path
    exercised with a tiny CPU-safe config" WP-34's own brief asks for.
    Without it, this targets a real GPU run (the operator's own step -
    this repo's sandbox has no GPU to run it in)."""
    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    base_ref = base_model_ref or config.base_model
    tokenizer = AutoTokenizer.from_pretrained(base_ref)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    # bf16 on the GPU path (ADR-0518): transformers' default fp32 load
    # would need ~36GB of host RAM for the Qwen3.5-9B base - over the
    # train pod's memory limit - where bf16 (the checkpoint's native
    # dtype) halves that. cpu_safe keeps the default: fp32 is the safe
    # dtype for CPU-only Trainer runs.
    model = AutoModelForCausalLM.from_pretrained(
        base_ref,
        **({} if config.cpu_safe else {"torch_dtype": torch.bfloat16}),
    )

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
    )
    model = get_peft_model(model, lora_config)

    dataset = Dataset.from_list([{"text": ex["text"]} for ex in examples])

    def _tokenize(batch):
        return tokenizer(batch["text"], truncation=True, padding="max_length", max_length=256)

    tokenized = dataset.map(_tokenize, batched=True, remove_columns=["text"])

    args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=1 if config.cpu_safe else 3,
        max_steps=5 if config.cpu_safe else -1,
        per_device_train_batch_size=1 if config.cpu_safe else 8,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        use_cpu=config.cpu_safe or not torch.cuda.is_available(),
    )
    trainer = Trainer(model=model, args=args, train_dataset=tokenized)
    train_result = trainer.train()

    model.save_pretrained(str(output_dir / "adapter"))
    tokenizer.save_pretrained(str(output_dir / "adapter"))

    return {"train_loss": getattr(train_result, "training_loss", None), "steps": trainer.state.global_step}


def stage_train_lora(config: MlopsConfig, store: ArtifactStore) -> None:
    import tempfile

    manifest = _load_dataset_manifest(config, store)
    examples_raw = store.get_bytes(f"{_run_prefix(config.dataset_prefix, config)}/examples.jsonl")
    if examples_raw is None:
        raise SystemExit(f"no examples.jsonl for {config.agent}/{config.run_id} - run prepare-dataset first")
    examples = [json.loads(line) for line in examples_raw.decode("utf-8").splitlines() if line.strip()]

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        # Resolved inside the TemporaryDirectory so an s3://-staged base
        # model's ~18GB working copy is reclaimed with the run.
        base_model_ref = _resolve_base_model(config, store, output_dir)
        train_stats = _run_lora_training(config, examples, output_dir, base_model_ref=base_model_ref)
        adapter_prefix = f"{_run_prefix(config.model_prefix, config)}/adapter"
        uploaded = store.put_dir(adapter_prefix, output_dir / "adapter")

    train_manifest = {
        "agent": config.agent,
        "run_id": config.run_id,
        "base_model": config.base_model,
        "lora_r": config.lora_r,
        "lora_alpha": config.lora_alpha,
        "lora_dropout": config.lora_dropout,
        "cpu_safe": config.cpu_safe,
        "classification": manifest["classification"],
        "example_count": manifest["example_count"],
        "adapter_s3_prefix": adapter_prefix,
        "adapter_files": uploaded,
        "train_stats": train_stats,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.put_json(f"{_run_prefix(config.model_prefix, config)}/train_manifest.json", train_manifest)
    logger.info("train-lora: adapter for %s/%s uploaded to %s (%d files)",
                config.agent, config.run_id, adapter_prefix, len(uploaded))


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def stage_evaluate(config: MlopsConfig, store: ArtifactStore) -> None:
    """ADR-0302 point 5: the same acceptance mechanism a base-model
    change would need, reused rather than a parallel harness -
    evaluations/quality_gate.py's own `evaluate()` (ADR-0107), which in
    turn subprocess-invokes evaluations/<agent>/run_acceptance_gate.py
    (the target agent's real 20-scenario/security-checks/gate-checks
    suite) and re-derives PASS/FAIL from that agent's own
    gate_config.yaml threshold."""
    train_manifest = store.get_json(f"{_run_prefix(config.model_prefix, config)}/train_manifest.json")
    if train_manifest is None:
        raise SystemExit(f"no train_manifest.json for {config.agent}/{config.run_id} - run train-lora first")

    sys.path.insert(0, config.evaluations_dir)
    from quality_gate import QualityGateError, evaluate as quality_gate_evaluate  # noqa: E402

    try:
        result = quality_gate_evaluate(config.agent, candidate=config.run_id)
    except QualityGateError as exc:
        result = {
            "agent": config.agent,
            "candidate": config.run_id,
            "overall": "FAIL",
            "error": str(exc),
        }

    result["adapter_s3_prefix"] = train_manifest["adapter_s3_prefix"]
    result["classification"] = train_manifest["classification"]
    store.put_json(f"{_run_prefix(config.eval_prefix, config)}/gate_result.json", result)
    logger.info("evaluate: %s/%s gate result %s", config.agent, config.run_id, result.get("overall"))
    if result.get("overall") != "PASS":
        # Non-zero exit fails the KFP task, stopping the DAG before
        # push-registry ever runs - the pipeline-level enforcement of
        # ADR-0302's "no bypass" requirement, on top of push-registry's
        # own independent check of the same fact (defense in depth).
        raise SystemExit(f"evaluate: gate result for {config.agent}/{config.run_id} is not PASS")


# --------------------------------------------------------------------------
# push-registry
# --------------------------------------------------------------------------


def _model_registry_base_url(config: MlopsConfig) -> str:
    if config.model_registry_url:
        return config.model_registry_url.rstrip("/")
    # In-cluster default: one Model Registry instance per registered name,
    # namespace read from the real Helm value (D5 - see MlopsConfig's own
    # field comment), never the stale zuno-ai-build the ADRs' original
    # Decision text assumed.
    return f"http://modelregistry-sample.{config.model_registry_namespace}.svc.cluster.local:8080"


def stage_push_registry(config: MlopsConfig, store: ArtifactStore) -> None:
    """ADR-0302 point 6/7: registers a PASSING adapter in the OpenShift AI
    Model Registry. Never touches gitops/charts/models/values.yaml -
    promotion to serving stays a human-reviewed GitOps PR (point 7);
    this stage's only side effect is a Model Registry API call plus one
    S3 write recording the result.

    ADR-0302 point 5/Security considerations: refuses to run - no
    request is made - if evaluate's own gate_result.json is missing or
    not PASS. This is the second, independent enforcement of "no bypass"
    (evaluate's own non-zero exit is the first, at the KFP-task level)."""
    gate_result = store.get_json(f"{_run_prefix(config.eval_prefix, config)}/gate_result.json")
    if gate_result is None or gate_result.get("overall") != "PASS":
        raise SystemExit(
            f"push-registry refuses to run for {config.agent}/{config.run_id}: "
            f"no passing gate_result.json found (ADR-0302 point 5, no bypass)"
        )
    train_manifest = store.get_json(f"{_run_prefix(config.model_prefix, config)}/train_manifest.json")
    if train_manifest is None:
        raise SystemExit(f"no train_manifest.json for {config.agent}/{config.run_id}")

    base_url = _model_registry_base_url(config)
    model_name = f"{config.agent}-lora"
    version_name = config.run_id

    registered_model = requests.post(
        f"{base_url}/api/model_registry/v1alpha3/registered_models",
        json={"name": model_name, "description": f"LoRA adapter for {config.agent} (ADR-0301/WP-34)"},
        timeout=30,
    )
    registered_model.raise_for_status()
    registered_model_id = registered_model.json()["id"]

    model_version = requests.post(
        f"{base_url}/api/model_registry/v1alpha3/registered_models/{registered_model_id}/versions",
        json={
            "name": version_name,
            "description": f"base_model={train_manifest['base_model']} lora_r={train_manifest['lora_r']}",
            "customProperties": {
                "classification": {"string_value": train_manifest["classification"], "metadataType": "MetadataStringValue"},
                "base_model": {"string_value": train_manifest["base_model"], "metadataType": "MetadataStringValue"},
            },
        },
        timeout=30,
    )
    model_version.raise_for_status()
    model_version_id = model_version.json()["id"]

    artifact_uri = f"s3://{config.s3_bucket}/{train_manifest['adapter_s3_prefix']}"
    model_artifact = requests.post(
        f"{base_url}/api/model_registry/v1alpha3/model_versions/{model_version_id}/artifacts",
        json={"name": f"{model_name}-{version_name}-artifact", "uri": artifact_uri, "artifactType": "model-artifact"},
        timeout=30,
    )
    model_artifact.raise_for_status()

    registration = {
        "agent": config.agent,
        "run_id": config.run_id,
        "registered_model_id": registered_model_id,
        "model_version_id": model_version_id,
        "model_version_name": version_name,
        "artifact_uri": artifact_uri,
        "classification": train_manifest["classification"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store.put_json(f"{_run_prefix(config.registry_prefix, config)}/registration.json", registration)
    logger.info(
        "push-registry: registered %s version %s (model_version_id=%s) - "
        "promotion to serving still requires a human-reviewed PR against "
        "gitops/charts/models/values.yaml (ADR-0302 point 7)",
        model_name, version_name, model_version_id,
    )


# --------------------------------------------------------------------------
# CLI dispatch
# --------------------------------------------------------------------------

STAGE_FUNCTIONS = {
    "prepare-dataset": stage_prepare_dataset,
    "train-lora": stage_train_lora,
    "evaluate": stage_evaluate,
    "push-registry": stage_push_registry,
}


def main() -> int:
    parser = argparse.ArgumentParser(prog="mlops")
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument(
        "--run-id",
        help=(
            "overrides MLOPS_RUN_ID - the KFP pipeline (gitops/charts/mlops/files/"
            "pipeline.py.tpl) passes this as a per-run CLI argument (a dsl.PipelineParam, "
            "so it can't be baked into the per-agent ConfigMap the way MLOPS_AGENT is) "
            "rather than a static env var, so every stage in the same run shares one id."
        ),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.run_id:
        os.environ["MLOPS_RUN_ID"] = args.run_id
    config = load_config()
    logger.info("Starting mlops stage: %s (agent %s, run_id %s)", args.stage, config.agent, config.run_id)

    store = ArtifactStore(config)
    STAGE_FUNCTIONS[args.stage](config, store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
