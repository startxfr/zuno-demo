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
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import boto3
import psycopg
import requests
import yaml
from botocore.exceptions import ClientError

logger = logging.getLogger("mlops")

# Reproducibility, set at import time because cuBLAS reads this when it
# allocates its workspace - on the FIRST matmul, which is far inside
# Trainer.train(). Setting it next to torch.use_deterministic_algorithms()
# would be too late to matter, and torch then raises rather than silently
# running nondeterministically. setdefault, so an operator debugging a
# determinism failure can still override it from the pod env.
#
# Why this exists (measured, not precautionary): four runs of THIS
# pipeline on a byte-identical corpus with identical hyperparameters
# produced four different models. Their register scores on the same 79
# held-out prompts:
#
#   run 004853  marker 0.9114  opening 0.2278  degenerate 0  PASS
#   run 021857  marker 0.9367  opening 0.1772  degenerate 0  PASS
#   run 084716  marker 0.9114  opening 0.2278  degenerate 0  PASS
#   run 125359  marker 0.8861  opening 0.2405  degenerate 5  FAIL
#
# The seed was already fixed (TrainingArguments defaults to 42), so the
# spread came from nondeterministic CUDA kernels compounding over 208
# steps. That spread is wide enough to flip a gate half on its own, which
# makes any before/after comparison across a corpus change unattributable
# - the whole point of the tool-calling corpus work this precedes.
_CUBLAS_DETERMINISTIC_WORKSPACE = ":4096:8"
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", _CUBLAS_DETERMINISTIC_WORKSPACE)

STAGES = (
    "prepare-dataset",
    "train-lora",
    # ADR-0526 (WP-087) decision 1: merges the adapter into a standalone
    # bf16 checkpoint. Between train and evaluate because the registered
    # artifact URI must be the merged checkpoint, not the adapter.
    "merge-export",
    "evaluate",
    "push-registry",
)

# ADR-0034's own escalation order, mirrored here (never re-derived from a
# different source of truth - see components/agent-runtime/app/graph/
# nodes.py's _escalate for the live-turn equivalent of this same rule).
_CLASSIFICATION_ORDER = {"C1": 1, "C2": 2, "C3": 3}


def _enable_deterministic_training(torch, config: "MlopsConfig") -> None:
    """Makes a training run reproducible from its seed alone.

    transformers' set_seed() (which TrainingArguments(seed=...) calls)
    only seeds the RNGs. It does not stop cuDNN from benchmarking kernel
    variants per run, and it does not stop CUDA ops from accumulating in
    nondeterministic order - which is what actually moved the four runs
    documented at the top of this module.

    Deliberately NOT warn_only=True: a warning here would restore exactly
    the failure mode this closes, a run that looks reproducible and is
    not.
    """
    if not config.deterministic:
        logger.warning(
            "MLOPS_DETERMINISTIC=false - training is nondeterministic and two runs "
            "of this config will not be comparable"
        )
        return

    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != _CUBLAS_DETERMINISTIC_WORKSPACE:
        logger.warning(
            "CUBLAS_WORKSPACE_CONFIG is %r, not %r - determinism may not hold",
            os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
            _CUBLAS_DETERMINISTIC_WORKSPACE,
        )
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    logger.info("deterministic training enabled (seed %d)", config.seed)


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

    # Reproducibility. seed is passed to TrainingArguments explicitly
    # rather than left to its default: the default is also 42, but an
    # implicit one is invisible at the call site and silently follows
    # whatever the installed transformers decides tomorrow.
    #
    # deterministic gates torch.use_deterministic_algorithms(). It is an
    # escape hatch, not a tuning knob: torch RAISES on any op with no
    # deterministic kernel, and that would abort a training run that has
    # already paid for a burst-node scale-up. If that ever happens, the
    # honest fix is a deterministic implementation of the offending op -
    # turning this off buys a green run at the cost of the comparison the
    # run exists to make.
    seed: int
    deterministic: bool

    # ADR-0526 (WP-087) decision 3: a NEW data-collection surface, added
    # deliberately. This OVERRIDES ADR-0302 point 2, which restricted
    # datasets to document_embeddings plus evaluation transcripts and
    # stated that "no new data-collection surface is introduced" - a
    # register-shift objective cannot be expressed in either source. When
    # set, prepare-dataset takes the style-corpus branch and never opens a
    # Postgres connection at all. The corpus is C1 by construction
    # (synthetic conversational style material, no business, customer or
    # financial content), so the escalate-only rule leaves the dataset -
    # and therefore the trained artifact - at C1.
    style_corpus_s3uri: Optional[str]

    # ADR-0526 decision 1: where merge-export publishes the merged bf16
    # checkpoint. This is the SAME bucket/prefix gitops/charts/models'
    # modelsS3 serves every model from (<prefix>/<servedModelName>/), so
    # promotion is a values.yaml change and nothing else.
    merged_model_s3uri: Optional[str]
    # Refuses to overwrite a non-empty destination unless this is set. The
    # destination is a prefix a running KServe storage-initializer reads:
    # on a re-run, silently replacing it would swap the weights under a
    # live model without the human review ADR-0302 point 7 requires.
    merged_overwrite: bool

    # The models bucket lives in a DIFFERENT REGION from this pipeline's
    # own artifact bucket (eu-west-2 vs us-east-1). boto3 will not follow
    # that redirect on a client built for the wrong region - it raises
    # PermanentRedirect - so the base-model download and the merged upload
    # need their own client. Same Vault credential (rag/s3) grants both.
    models_s3_region: Optional[str]
    models_s3_endpoint: Optional[str]

    # peft LoraConfig.target_modules. A single string is matched with
    # re.fullmatch against the FULL module key, which is what makes the
    # `model.language_model.layers.` anchor able to exclude the mtp.*
    # multi-token-prediction head and the vision tower structurally. See
    # _run_lora_training for why a suffix list is not safe on this
    # architecture.
    lora_target_modules: Optional[str]

    # evaluations/<agent>/quality_gate.py integration.
    evaluations_dir: str
    # WP-087 phase 2: the tool-probe half reads the target task's own
    # prompt body from agents/<agent>/tasks/<task>.md, which the image
    # already carries (Containerfile COPY agents).
    agents_dir: str

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
    # The registered model's name. Defaults to "<agent>-lora" for
    # backwards compatibility with WP-34's own naming.
    registered_model_name: Optional[str]
    # ADR-0526/WP-087: the in-cluster Model Registry is HTTPS with an
    # Authorization header, not the plain-HTTP unauthenticated
    # modelregistry-sample:8080 WP-34 assumed (that Service exists
    # nowhere). Every part is a value rather than a literal: nothing in
    # this repository creates or names a ModelRegistry instance, so these
    # are operator observations - UNVERIFIED against a live cluster.
    model_registry_service: str
    model_registry_port: int
    model_registry_scheme: str
    model_registry_ca_bundle: Optional[str]
    model_registry_token_path: Optional[str]


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
        seed=_env_int("MLOPS_SEED", 42),
        deterministic=_env_bool("MLOPS_DETERMINISTIC", True),
        style_corpus_s3uri=_env("MLOPS_STYLE_CORPUS_S3URI"),
        merged_model_s3uri=_env("MLOPS_MERGED_MODEL_S3URI"),
        merged_overwrite=_env_bool("MLOPS_MERGED_OVERWRITE", False),
        models_s3_region=_env("MLOPS_MODELS_S3_REGION"),
        models_s3_endpoint=_env("MLOPS_MODELS_S3_ENDPOINT"),
        lora_target_modules=_env("MLOPS_LORA_TARGET_MODULES"),
        evaluations_dir=_env("MLOPS_EVALUATIONS_DIR", "/opt/app-root/src/evaluations"),
        agents_dir=_env("MLOPS_AGENTS_DIR", "/opt/app-root/src/agents"),
        model_registry_url=_env("MODEL_REGISTRY_URL"),
        model_registry_namespace=_env("MODEL_REGISTRY_NAMESPACE", "rhoai-model-registries"),
        registered_model_name=_env("MLOPS_REGISTERED_MODEL_NAME"),
        model_registry_service=_env("MODEL_REGISTRY_SERVICE", "zuno"),
        model_registry_port=_env_int("MODEL_REGISTRY_PORT", 8443),
        model_registry_scheme=_env("MODEL_REGISTRY_SCHEME", "https"),
        model_registry_ca_bundle=_env(
            "MODEL_REGISTRY_CA_BUNDLE", "/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt"
        ),
        model_registry_token_path=_env(
            "MODEL_REGISTRY_TOKEN_PATH", "/var/run/secrets/kubernetes.io/serviceaccount/token"
        ),
    )


# --------------------------------------------------------------------------
# S3 state store - same four-method shape as components/rag-ingestion's
# own CorpusStore, plus put_bytes (adapter files are binary, not JSON).
# --------------------------------------------------------------------------


class ArtifactStore:
    """One credential, possibly several regions.

    WP-087: this pipeline's own artifact bucket (S3_BUCKET, us-east-1) and
    the models bucket the base checkpoint and the merged export live in
    (zuno-demo-rag-corpus, eu-west-2) are in DIFFERENT regions. A boto3
    client built for one region does not follow the redirect to the other -
    it raises PermanentRedirect - so a single shared client cannot serve
    both. Clients are therefore cached per (region, endpoint) and built on
    demand from the same credential; the default one keeps serving every
    call that does not ask for an override, so nothing else changes.
    """

    def __init__(self, config: MlopsConfig):
        self._bucket = config.s3_bucket
        self._path_style = config.s3_path_style
        self._access_key = config.aws_access_key_id
        self._secret_key = config.aws_secret_access_key
        self._default_region = config.s3_region or None
        self._default_endpoint = config.s3_endpoint or None
        self._clients: Dict[tuple, Any] = {}
        self._client = self._client_for(self._default_region, self._default_endpoint)

    def _client_for(self, region: Optional[str], endpoint: Optional[str]):
        key = (region or None, endpoint or None)
        cached = self._clients.get(key)
        if cached is not None:
            return cached
        from botocore.config import Config as BotoClientConfig

        client_kwargs: dict = {
            "region_name": key[0],
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "config": BotoClientConfig(s3={"addressing_style": "path" if self._path_style else "auto"}),
        }
        if key[1]:
            client_kwargs["endpoint_url"] = key[1]
        client = boto3.client("s3", **client_kwargs)
        self._clients[key] = client
        return client

    def _resolve(self, bucket: Optional[str], region: Optional[str], endpoint: Optional[str]):
        """Every cross-bucket call goes through here, so "which client for
        which bucket" is decided in exactly one place.

        An explicit region override must NOT inherit the default endpoint.
        S3_ENDPOINT is region-pinned here (the chart derives
        https://s3.<region>.amazonaws.com), so falling back to it while
        overriding region_name builds a client aimed at eu-west-2 that
        still dials the us-east-1 host - and AWS answers PermanentRedirect.
        Region and endpoint travel together or not at all: when a caller
        names a region and no endpoint, pass None and let boto3 derive the
        regional endpoint itself.
        """
        if bucket is None or bucket == self._bucket:
            return (self._bucket if bucket is None else bucket), self._client
        if region:
            return bucket, self._client_for(region, endpoint or None)
        return bucket, self._client_for(self._default_region, endpoint or self._default_endpoint)

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

    @property
    def bucket(self) -> str:
        return self._bucket

    def get_bytes(
        self,
        key: str,
        *,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> Optional[bytes]:
        target_bucket, client = self._resolve(bucket, region, endpoint)
        try:
            resp = client.get_object(Bucket=target_bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return resp["Body"].read()

    def put_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def list_keys(
        self,
        prefix: str,
        *,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> List[str]:
        target_bucket, client = self._resolve(bucket, region, endpoint)
        paginator = client.get_paginator("list_objects_v2")
        keys: List[str] = []
        for page in paginator.paginate(Bucket=target_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def put_dir(
        self,
        prefix: str,
        local_dir: Path,
        *,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> List[str]:
        """Uploads every file under local_dir, preserving relative paths
        under prefix - train-lora publishes an adapter's saved-checkpoint
        directory this way, and merge-export the merged model.

        upload_file, never put_bytes: an adapter is a few MB but a merged
        Qwen3.5-9B checkpoint is ~19GB across four shards, and buffering
        one 5GB shard in memory would blow the stage's memory limit. This
        is the upload mirror of download_prefix's own reason for using
        download_file."""
        target_bucket, client = self._resolve(bucket, region, endpoint)
        uploaded = []
        for path in sorted(local_dir.rglob("*")):
            if path.is_file():
                key = f"{prefix}/{path.relative_to(local_dir).as_posix()}"
                client.upload_file(str(path), target_bucket, key)
                uploaded.append(key)
        return uploaded

    def download_prefix(
        self,
        bucket: str,
        prefix: str,
        local_dir: Path,
        *,
        region: Optional[str] = None,
        endpoint: Optional[str] = None,
        include: Optional[Callable[[str], bool]] = None,
    ) -> int:
        """Downloads every object under s3://bucket/prefix/ into
        local_dir, preserving relative paths - train-lora's base-model
        fetch (ADR-0518). Takes an explicit bucket (the base model lives
        under the models/ prefix, addressed by a full s3:// URI in
        MLOPS_BASE_MODEL) but reuses this store's client/credentials.
        download_file streams to disk via boto3's managed transfer -
        never get_bytes: safetensors shards run ~5GB each and buffering
        one in memory would eat half the train pod's memory request.

        `include` filters by RELATIVE key, so a caller that only needs the
        tokenizer can take ~11MB instead of the full 19.3GB checkpoint -
        which is exactly what prepare-dataset does to render the chat
        template without ever touching the weights."""
        target_bucket, client = self._resolve(bucket, region, endpoint)
        prefix = prefix.rstrip("/") + "/"
        paginator = client.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=target_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(prefix):]
                if not rel:
                    continue
                if include is not None and not include(rel):
                    continue
                target = local_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(target_bucket, obj["Key"], str(target))
                count += 1
        return count


def _split_s3_uri(uri: str) -> tuple:
    """s3://bucket/prefix -> (bucket, prefix). One parser, so the base
    model, the style corpus and the merged destination cannot drift."""
    if not uri.startswith("s3://"):
        raise SystemExit(f"not an s3:// URI: {uri}")
    bucket, _, prefix = uri[len("s3://"):].partition("/")
    if not bucket or not prefix:
        raise SystemExit(f"malformed s3:// URI (need bucket and key/prefix): {uri}")
    return bucket, prefix.rstrip("/")


# Enough of the base checkpoint to render a chat template, and no more:
# ~11MB of tokenizer files against 19.3GB of weights. prepare-dataset runs
# on a plain CPU pod and has no business downloading safetensors.
_TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer_config.json",
    "tokenizer.model",
    "special_tokens_map.json",
    "chat_template.jinja",
    "vocab.json",
    "merges.txt",
    "generation_config.json",
)


def _resolve_base_model(config: MlopsConfig, store: ArtifactStore, workdir: Path) -> str:
    """Returns a from_pretrained-loadable reference for config.base_model:
    an s3://<bucket>/<prefix> URI (ADR-0518 - the staged-in-S3 base, same
    convention every served model follows) is downloaded under workdir
    and the local directory path returned; anything else (an HF repo id,
    a pre-mounted local path) passes through untouched."""
    if not config.base_model.startswith("s3://"):
        return config.base_model
    bucket, prefix = _split_s3_uri(config.base_model)
    local_dir = workdir / "base-model"
    local_dir.mkdir(parents=True, exist_ok=True)
    # region/endpoint overrides: the models bucket is in another region
    # than this pipeline's artifact bucket - see ArtifactStore's docstring.
    count = store.download_prefix(
        bucket, prefix, local_dir,
        region=config.models_s3_region, endpoint=config.models_s3_endpoint,
    )
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


def _download_style_corpus(config: MlopsConfig, store: ArtifactStore, workdir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """ADR-0526 decision 3: reads the staged French urban-register corpus.

    A single .tgz holding OpenAI Messages JSONL - one single-turn
    user/assistant conversation per line - split at SEED level, so
    paraphrases of a seed never cross a split boundary and the held-out
    test set is genuinely held out.

    Extraction is filtered rather than trusting the archive: a tar member
    whose name escapes the extraction root (absolute, or containing '..')
    is refused outright. The archive is ours today, but "we produced it"
    is not an access-control property, and this runs as a pod with the
    pipeline's own S3 credentials.
    """
    import tarfile

    bucket, key = _split_s3_uri(config.style_corpus_s3uri)
    # The corpus bucket is named by the URI, not assumed to be S3_BUCKET -
    # ArtifactStore._resolve picks the default client when they match and
    # a region-correct one when they do not.
    raw = store.get_bytes(key, bucket=bucket)
    if raw is None:
        raise SystemExit(f"style corpus not found at {config.style_corpus_s3uri}")

    root = workdir / "style-corpus"
    root.mkdir(parents=True, exist_ok=True)
    archive = workdir / "style-corpus.tgz"
    archive.write_bytes(raw)
    with tarfile.open(archive, "r:gz") as tar:
        safe = []
        for member in tar.getmembers():
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts:
                logger.warning("refusing unsafe tar member %s", member.name)
                continue
            if not (member.isfile() or member.isdir()):
                logger.warning("refusing non-regular tar member %s", member.name)
                continue
            safe.append(member)
        tar.extractall(root, members=safe)

    splits: Dict[str, List[Dict[str, Any]]] = {}
    for split in ("train", "validation", "test"):
        matches = sorted(root.rglob(f"{split}.jsonl"))
        if not matches:
            raise SystemExit(f"style corpus {config.style_corpus_s3uri} has no {split}.jsonl")
        rows = []
        for line in matches[0].read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        splits[split] = rows
    logger.info(
        "style corpus: %s train / %s validation / %s test conversations",
        len(splits["train"]), len(splits["validation"]), len(splits["test"]),
    )
    return splits


def _load_chat_tokenizer(config: MlopsConfig, store: ArtifactStore, workdir: Path):
    """Tokenizer only - the ~11MB of the base checkpoint needed to render
    a chat template, never the weights (see _TOKENIZER_FILES)."""
    from transformers import AutoTokenizer

    if not config.base_model.startswith("s3://"):
        return AutoTokenizer.from_pretrained(config.base_model)
    bucket, prefix = _split_s3_uri(config.base_model)
    local_dir = workdir / "tokenizer"
    local_dir.mkdir(parents=True, exist_ok=True)
    store.download_prefix(
        bucket, prefix, local_dir,
        region=config.models_s3_region, endpoint=config.models_s3_endpoint,
        include=lambda rel: rel in _TOKENIZER_FILES,
    )
    tokenizer = AutoTokenizer.from_pretrained(str(local_dir))
    if getattr(tokenizer, "chat_template", None) is None:
        # Verified present on the staged Qwen3.5-9B checkpoint
        # (chat_template.jinja, 2026-08-27), so this is a guard, not an
        # expected path - but a base model id is not a promise of one, and
        # silently training on un-templated text would produce a model
        # that never emits the turn structure vLLM serves.
        raise SystemExit(
            f"{config.base_model} has no chat_template; refusing to render the style corpus "
            f"with an invented one - stage a checkpoint that carries chat_template.jinja "
            f"or set one explicitly on the tokenizer"
        )
    return tokenizer


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


def _prepare_style_dataset(config: MlopsConfig, store: ArtifactStore) -> None:
    """ADR-0526 decision 3's branch: a style corpus, not domain grounding.

    Renders every conversation through the BASE MODEL'S OWN chat template,
    so training sees exactly the turn structure vLLM will serve at
    inference. Each example carries two fields:

      text   - the full rendered conversation (prompt + completion)
      prompt - the same render truncated to the generation prefix

    train-lora masks `prompt`'s tokens out of the loss. Without that
    split, full-sequence LM loss over 716 single-turn exchanges would also
    teach the model to generate USER turns in this register - a real
    quality regression, and free to avoid once the prefix is recorded here.

    Classification is C1 and stays C1: the corpus is synthetic
    conversational style material with no business, customer or financial
    content, and this branch never reads document_embeddings, so there is
    nothing that could escalate it (ADR-0034's rule is escalate-only).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        splits = _download_style_corpus(config, store, workdir)
        tokenizer = _load_chat_tokenizer(config, store, workdir)

        examples: List[Dict[str, Any]] = []
        skipped = 0
        for split in ("train", "validation"):
            for row in splits[split]:
                messages = row.get("messages") or []
                if len(messages) < 2 or messages[-1].get("role") != "assistant":
                    skipped += 1
                    continue
                # WP-087 phase 2: a corpus row may carry its own `tools`
                # array and an assistant turn holding `tool_calls`. The
                # staged checkpoint's chat_template.jinja handles `tools`,
                # `tool_calls` and the `tool` role (verified against the
                # real template), so rendering them needs no template work
                # - only that they are passed.
                #
                # BOTH renders must receive the SAME tools. _make_collator
                # masks by prompt_len, so a prefix rendered without the
                # schemas against a full text rendered with them shifts
                # every label by the length of the tool block: loss would
                # land on the wrong tokens and train the model on noise,
                # silently and with no error anywhere.
                tools = row.get("tools") or None
                kwargs = {"tools": tools} if tools else {}
                text = tokenizer.apply_chat_template(messages, tokenize=False, **kwargs)
                prompt = tokenizer.apply_chat_template(
                    messages[:-1], tokenize=False, add_generation_prompt=True, **kwargs
                )
                # The masking contract, asserted rather than assumed: the
                # prompt render must be a literal prefix of the full
                # render. If a future template emits the tool block only
                # in one of the two, this fails loudly here instead of
                # producing a silently mistrained adapter.
                if not text.startswith(prompt):
                    raise SystemExit(
                        "chat template rendered a prompt that is not a prefix of the full "
                        f"text (row {len(examples)} of {split}, tools={bool(tools)}) - "
                        "prompt_len masking would put the loss on the wrong tokens"
                    )
                examples.append({
                    "text": text,
                    "prompt": prompt,
                    "source": f"style-corpus/{split}",
                    # Recorded so a run can be audited for how much of its
                    # corpus actually exercised tool use, without re-reading
                    # the tarball.
                    "has_tools": bool(tools),
                })
        if skipped:
            logger.warning("skipped %d corpus rows without a trailing assistant turn", skipped)
        if not examples:
            raise SystemExit(f"style corpus {config.style_corpus_s3uri} yielded no usable examples")

        run_prefix = _run_prefix(config.dataset_prefix, config)
        store.put_text(
            f"{run_prefix}/examples.jsonl",
            "\n".join(json.dumps(ex, ensure_ascii=False) for ex in examples),
        )
        # Carried forward untouched for the register-conformance half of
        # the gate (ADR-0526 decision 8): train-lora generates completions
        # for these held-out prompts, evaluate scores them. Held out means
        # held out - nothing above ever trains on this split.
        store.put_text(
            f"{run_prefix}/test.jsonl",
            "\n".join(json.dumps(r, ensure_ascii=False) for r in splits["test"]),
        )

        manifest = {
            "agent": config.agent,
            "run_id": config.run_id,
            "objective": "style-register",
            "corpus_uri": config.style_corpus_s3uri,
            "split_counts": {k: len(v) for k, v in splits.items()},
            "example_count": len(examples),
            "grounding_row_count": 0,
            "scenario_seed_count": 0,
            "test_example_count": len(splits["test"]),
            "classification": "C1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        store.put_json(f"{run_prefix}/dataset_manifest.json", manifest)
        logger.info(
            "prepare-dataset: %d style examples + %d held-out test prompts for %s/%s (C1)",
            len(examples), len(splits["test"]), config.agent, config.run_id,
        )


def stage_prepare_dataset(config: MlopsConfig, store: ArtifactStore) -> None:
    # ADR-0526 decision 3 overrides ADR-0302 point 2 for this objective
    # only. The two branches are mutually exclusive by design: a style
    # corpus and domain-grounding rows train different things, and mixing
    # them would make the dataset's classification depend on which source
    # happened to dominate.
    if config.style_corpus_s3uri:
        _prepare_style_dataset(config, store)
        return
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


def _resolve_model_class(checkpoint_dir: str):
    """Returns the transformers class that can load this checkpoint.

    Reads the checkpoint's OWN config.json rather than picking an Auto*
    class by hand. WP-34 used AutoModelForCausalLM, which is wrong here:
    the staged checkpoint declares Qwen3_5ForConditionalGeneration with a
    vision tower, and *ForConditionalGeneration architectures with a
    vision config register under AutoModelForImageTextToText, not
    AutoModelForCausalLM. Guessing between them is a coin flip that fails
    at from_pretrained; reading architectures[0] is deterministic,
    independent of the installed transformers version, and - decisively -
    unit-testable offline with a stub module, which no Auto* choice is.
    """
    import transformers

    config_path = Path(checkpoint_dir) / "config.json"
    arch = None
    if config_path.is_file():
        declared = (json.loads(config_path.read_text(encoding="utf-8")) or {}).get("architectures") or []
        arch = declared[0] if declared else None

    if arch:
        cls = getattr(transformers, arch, None)
        if cls is not None:
            logger.info("resolved model class %s from the checkpoint's own config.json", arch)
            return cls
        logger.warning(
            "checkpoint declares %s but the installed transformers (%s) does not export it; "
            "falling back to an Auto* class",
            arch, getattr(transformers, "__version__", "unknown"),
        )

    for name in ("AutoModelForImageTextToText", "AutoModelForVision2Seq", "AutoModelForCausalLM"):
        cls = getattr(transformers, name, None)
        if cls is not None:
            logger.info("using %s for %s", name, arch or "an undeclared architecture")
            return cls
    raise SystemExit(
        f"cannot load architecture {arch!r}: installed transformers "
        f"{getattr(transformers, '__version__', 'unknown')} exports neither it nor any usable Auto* class"
    )


def _make_collator(pad_token_id: int):
    """Pads to the batch maximum and builds `labels`.

    Two things, both load-bearing:

    1. WP-34's tokenize step passed neither `labels` nor a collator that
       synthesizes them, and transformers' default_data_collator does not
       - so Trainer.train() had no loss to compute. The pipeline has never
       run, so this never surfaced.
    2. Prompt tokens are masked to -100, so loss is computed on the
       ASSISTANT completion only. Full-sequence loss over single-turn
       exchanges would also train the model to produce user turns in this
       register, which is a real quality regression and free to avoid now
       that prepare-dataset records the prompt prefix.
    """
    import torch

    def collate(features):
        width = max(len(f["input_ids"]) for f in features)
        input_ids, attention, labels = [], [], []
        for f in features:
            ids = list(f["input_ids"])
            mask = list(f.get("attention_mask") or [1] * len(ids))
            lab = list(ids)
            for i in range(min(int(f.get("prompt_len", 0)), len(lab))):
                lab[i] = -100
            pad = width - len(ids)
            input_ids.append(ids + [pad_token_id] * pad)
            attention.append(mask + [0] * pad)
            labels.append(lab + [-100] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }

    return collate


def _run_lora_training(
    config: MlopsConfig,
    examples: List[Dict[str, Any]],
    output_dir: Path,
    base_model_ref: Optional[str] = None,
    held_out: Optional[List[Dict[str, Any]]] = None,
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
    from transformers import AutoTokenizer, Trainer, TrainingArguments

    _enable_deterministic_training(torch, config)

    base_ref = base_model_ref or config.base_model
    tokenizer = AutoTokenizer.from_pretrained(base_ref)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    # bf16 on the GPU path (ADR-0518): transformers' default fp32 load
    # would need ~36GB of host RAM for the Qwen3.5-9B base - over the
    # train pod's memory limit - where bf16 (the checkpoint's native
    # dtype) halves that. cpu_safe keeps the default: fp32 is the safe
    # dtype for CPU-only Trainer runs.
    model_class = _resolve_model_class(base_ref)
    model = model_class.from_pretrained(
        base_ref,
        **({} if config.cpu_safe else {"torch_dtype": torch.bfloat16}),
    )

    # A LoraConfig with no target_modules leaves peft to guess from its own
    # per-architecture table, which has no entry for qwen3_5 - so nothing
    # is wrapped, nothing trains, and the merge is a no-op that produces a
    # perfect copy of the base. See values.yaml's loraTargetModules for why
    # this is an anchored regex rather than a suffix list.
    lora_kwargs: Dict[str, Any] = {}
    if config.lora_target_modules:
        lora_kwargs["target_modules"] = config.lora_target_modules
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        **lora_kwargs,
    )
    model = get_peft_model(model, lora_config)

    # Fail loudly on a regex that matched nothing. Without this the run is
    # green end to end and the served variant is byte-identical to its
    # base - the most expensive possible way to learn that a pattern was
    # wrong (a full burst-node training run, then a live A/B that shows no
    # difference).
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    wrapped = sum(1 for name, _ in model.named_modules() if name.endswith("lora_A.default"))
    logger.info("LoRA wrapped %d modules, %d trainable parameters", wrapped, trainable)
    if trainable == 0 or wrapped == 0:
        raise SystemExit(
            f"LoRA matched no modules (target_modules={config.lora_target_modules!r}) - "
            f"training would be a no-op and the merged checkpoint identical to the base"
        )

    # prompt_len drives the collator's -100 masking. Computed per example
    # against the SAME tokenizer, so the boundary is exact rather than a
    # string-length approximation.
    def _encode(ex: Dict[str, Any]) -> Dict[str, Any]:
        full = tokenizer(ex["text"], truncation=True, max_length=max_length)
        prompt_len = 0
        if ex.get("prompt"):
            prompt_len = len(tokenizer(ex["prompt"], truncation=True, max_length=max_length)["input_ids"])
        return {
            "input_ids": full["input_ids"],
            "attention_mask": full["attention_mask"],
            "prompt_len": min(prompt_len, len(full["input_ids"])),
        }

    max_length = 256 if config.cpu_safe else 1024
    dataset = Dataset.from_list([dict(ex) for ex in examples])
    tokenized = dataset.map(_encode, remove_columns=list(dataset.column_names))

    args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        # Two, bracketed by two real runs rather than guessed. Both ends
        # were measured on the same 79 held-out prompts, ADR-0526's own
        # register gate scoring them:
        #
        #   3 epochs -> opening rate 44.3% (ceiling 30%), marker rate 100%
        #   1 epoch  -> opening rate  0.0%, marker rate 60.8% (floor 70%)
        #
        # So 3 memorises one opening formula and 1 does not acquire the
        # register at all - the corpus itself opens with "wesh" 5.95% of
        # the time. The window is wide and 2 is the only value inside the
        # bracket; if it also misses, the bracket has narrowed rather than
        # the approach having failed.
        num_train_epochs=2,
        max_steps=5 if config.cpu_safe else -1,
        per_device_train_batch_size=1 if config.cpu_safe else 8,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="no",
        seed=config.seed,
        report_to=[],
        use_cpu=config.cpu_safe or not torch.cuda.is_available(),
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=tokenized,
        data_collator=_make_collator(tokenizer.pad_token_id),
    )
    train_result = trainer.train()

    model.save_pretrained(str(output_dir / "adapter"))
    tokenizer.save_pretrained(str(output_dir / "adapter"))

    stats = {"train_loss": getattr(train_result, "training_loss", None), "steps": trainer.state.global_step}
    if held_out:
        stats["register_samples"] = _generate_held_out(model, tokenizer, held_out, cpu_safe=config.cpu_safe)
    # WP-087 phase 2: the tool-calling half, produced on the same GPU that
    # just finished training, for the same reason the register samples are
    # (ADR-0526 decision 8's own note): the merged model is deployed
    # nowhere when the gate runs. Independent of held_out - a probe set
    # exists per agent, not per corpus split.
    probes = _load_tool_probes(config)
    if probes:
        stats["tool_samples"] = _generate_tool_probes(model, tokenizer, config, probes)
    return stats


# A chat-templated generation prefix ends INSIDE the assistant turn, and on
# a Qwen3 template it also opens a <think> block. Two consequences bit the
# first real run (wesh-20260827-220749), and both silently corrupted the
# ADR-0526 decision 8 score rather than failing:
#
#  - generate() stops on generation_config.json's eos, which on a BASE
#    checkpoint is <|endoftext|>, not the chat template's <|im_end|>. So
#    every one of the 79 samples ran past its own answer and re-opened a
#    fabricated user/assistant turn, doubling the scored text.
#  - what remains still starts with the model's REASONING, not its answer.
#    The register score was therefore computed over reasoning plus a
#    hallucinated second turn.
#
# Measured on that run's stored samples: scoring the real answer moves the
# rule-3 opening rate from 31.6% to 44.3% - the contaminated reading was
# not merely noisy, it under-reported the failure it was meant to catch.
_ROLE_RESTART = re.compile(r"\n\s*(assistant|user|system)\s*\n")


def _load_tool_probes(config: MlopsConfig) -> Optional[Dict[str, Any]]:
    """Reads evaluations/<agent>/tool_probes.yaml, or None if absent.

    Absent is legitimate: only agents whose tasks bind model-facing tools
    have a probe set, and a grounding-domain run has none at all. The file
    carries the tool SCHEMAS as well as the probes, because the mlops image
    ships evaluations/ and agents/ but not components/agent-runtime - a
    drift test in evaluations/tests/ is what keeps the copy honest.
    """
    path = Path(config.evaluations_dir) / config.agent / "tool_probes.yaml"
    if not path.is_file():
        return None
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not doc.get("probes") or not doc.get("tool_schemas"):
        logger.warning("%s exists but declares no probes/tool_schemas; skipping the tool half", path)
        return None
    return doc


def _task_system_prompt(config: MlopsConfig, task_name: str) -> str:
    """The task's own prompt body, the same text agent-runtime sends as the
    system message. Load-bearing: the regression this measures does NOT
    appear without a system prompt - probed bare, the variant still calls
    correctly - so a probe set that omitted it would score green and prove
    nothing."""
    path = Path(config.agents_dir) / config.agent / "tasks" / f"{task_name}.md"
    raw = path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise SystemExit(f"{path} has no YAML frontmatter; cannot recover its prompt body")
    return parts[2].strip()


def _generate_tool_probes(model, tokenizer, config: MlopsConfig, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Replays the probe set against the freshly trained model.

    Produces exactly the record shape
    evaluations/tool_calling_conformance.score_probe consumes, so the
    evaluate stage scores it with no reshaping. Greedy, for the same
    reproducibility reason _generate_held_out is greedy.

    max_new_tokens is deliberately generous: a mermaid argument runs to
    ~900 characters and a tight budget truncates it mid-JSON, which scores
    as a broken call when the model in fact behaved correctly. That
    happened while establishing the phase 1 baseline and cost a wrong
    conclusion about the base model until it was re-measured.
    """
    import torch

    schemas = doc["tool_schemas"]
    required = {
        sch["function"]["name"]: sch["function"].get("parameters", {}).get("required", [])
        for sch in schemas
    }
    offered = [sch["function"]["name"] for sch in schemas]
    system = _task_system_prompt(config, doc["task"])
    stop_ids = _chat_stop_token_ids(tokenizer)
    probes = doc["probes"][:4] if config.cpu_safe else doc["probes"]

    results: List[Dict[str, Any]] = []
    model.eval()
    with torch.no_grad():
        for probe in probes:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Context:\n\nQuestion: {probe['message']}"},
            ]
            text = tokenizer.apply_chat_template(
                messages, tools=schemas, tokenize=False, add_generation_prompt=True
            )
            enc = tokenizer(text, return_tensors="pt").to(model.device)
            out = model.generate(
                **enc,
                max_new_tokens=64 if config.cpu_safe else 1500,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                **({"eos_token_id": stop_ids} if stop_ids else {}),
            )
            decoded = tokenizer.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=False)
            calls = _parse_tool_calls(decoded)
            expected = probe.get("expects_tool") or ""
            results.append({
                "id": probe["id"],
                "expects_tool": bool(expected),
                "expected_tool": expected,
                "required_arguments": required.get(expected, []),
                "offered_tools": offered,
                "tool_calls": calls,
                "content": _extract_answer(_strip_tool_calls(decoded)),
                "raw": decoded,
            })
    logger.info("generated %d tool-probe responses for the tool-calling half", len(results))
    return results


# vLLM applies --tool-call-parser server-side; here we decode raw, so the
# call block has to be read out of the text. Qwen3 emits it inside
# <tool_call>...</tool_call> as a JSON object with name/arguments.
# Qwen3.5 emits tool calls as XML, NOT as JSON - which is why the serving
# args set --tool-call-parser=qwen3_xml. Verified against the staged
# checkpoint's own chat_template.jinja, whose instruction block reads:
#
#   <tool_call>
#   <function=example_function_name>
#   <parameter=example_parameter_1>
#   value_1
#   </parameter>
#   </function>
#   </tool_call>
#
# A JSON-shaped parser finds nothing here, on every decode, for every
# model - so the tool half would have reported "0 calls" for a healthy
# model exactly as loudly as for the broken one, and the metric added to
# catch a silent regression would itself have been silently wrong.
#
# The unterminated pattern is not padding: a mermaid parameter runs to
# ~900 characters, and generation hitting its token budget mid-parameter
# cuts off the closing tags with everything else. Reporting "no call" for
# that blames the model for a harness limit.
_TOOL_CALL_BLOCK = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.S)
_TOOL_CALL_UNTERMINATED = re.compile(r"<tool_call>\s*((?:(?!</tool_call>).)*)\Z", re.S)
_TOOL_FUNCTION = re.compile(r"<function=([^>\s]+)\s*>(.*?)(?:</function>|\Z)", re.S)
_TOOL_PARAMETER = re.compile(r"<parameter=([^>\s]+)\s*>\s*(.*?)\s*(?:</parameter>|\Z)", re.S)


def _parse_tool_calls(decoded: str) -> List[Dict[str, Any]]:
    """Tool calls in the raw decode, normalized to {"name", "arguments"}
    with arguments as a JSON string - the shape the OpenAI-compatible API
    returns, so the scorer is fed identically whether a sample came from
    here or from a served endpoint.

    A block that yields no <function=...> is recorded with an empty name
    rather than dropped: that is a broken call, and the scorer must count
    it as one instead of as an abstention.
    """
    text = decoded or ""
    blobs = list(_TOOL_CALL_BLOCK.findall(text))
    tail = _TOOL_CALL_UNTERMINATED.search(text)
    if tail and tail.group(1).strip():
        blobs.append(tail.group(1))

    calls: List[Dict[str, Any]] = []
    for blob in blobs:
        functions = _TOOL_FUNCTION.findall(blob)
        if not functions:
            calls.append({"name": "", "arguments": blob.strip()})
            continue
        for name, body in functions:
            args = {key: value for key, value in _TOOL_PARAMETER.findall(body)}
            calls.append({"name": name.strip(), "arguments": json.dumps(args, ensure_ascii=False)})
    return calls


def _strip_tool_calls(decoded: str) -> str:
    """The prose beside any tool call - what the narration detector reads."""
    return _TOOL_CALL_BLOCK.sub(" ", decoded or "")


def _chat_stop_token_ids(tokenizer) -> List[int]:
    """Stop ids for a chat-templated decode, widest-first.

    Returns the template's own end-of-turn token alongside whatever the
    tokenizer calls eos, because on a base checkpoint those differ and
    only the former actually terminates an assistant turn.
    """
    ids: List[int] = []
    unk = getattr(tokenizer, "unk_token_id", None)
    for token in ("<|im_end|>", "<|endoftext|>"):
        try:
            tid = tokenizer.convert_tokens_to_ids(token)
        except Exception:  # a tokenizer without this vocabulary at all
            continue
        if isinstance(tid, int) and tid >= 0 and tid != unk and tid not in ids:
            ids.append(tid)
    eos = getattr(tokenizer, "eos_token_id", None)
    if isinstance(eos, int) and eos not in ids:
        ids.append(eos)
    return ids


def _extract_answer(decoded: str) -> str:
    """The assistant's answer alone, from a raw chat-template decode.

    Drops the reasoning block the template opens (everything up to and
    including the last </think>) and anything after the model restarts a
    turn. Both guards are belt-and-braces alongside the stop ids above:
    a model that emits no </think> keeps its whole output.
    """
    if "</think>" in decoded:
        # FIRST occurrence, not last: when the model also restarts a turn
        # it opens a second <think> block, and rsplit would return that
        # fabricated turn's answer instead of this turn's. Stripping the
        # reasoning must also come BEFORE the role-restart cut - a
        # reasoning block that itself rambles into a fake user turn would
        # otherwise be mistaken for the answer.
        decoded = decoded.split("</think>", 1)[1]
    match = _ROLE_RESTART.search(decoded)
    if match:
        decoded = decoded[: match.start()]
    return decoded.strip()


def _generate_held_out(model, tokenizer, held_out: List[Dict[str, Any]], *, cpu_safe: bool) -> List[Dict[str, Any]]:
    """Generates completions for the held-out prompts, here in train-lora.

    ADR-0526 decision 8 needs the candidate's own output to score, but the
    merged model is deployed NOWHERE when the gate runs: evaluate runs
    before push-registry, and promotion to serving is a later human PR. So
    the samples are produced on the GPU that just finished training,
    rather than by calling a service that does not exist yet.

    Scoring the PEFT model rather than the merged one is equivalent:
    merge_and_unload() computes W + (alpha/r).B.A, and the eval-mode LoRA
    forward computes W.x + (alpha/r).B(A(x)) - the same function up to bf16
    rounding, with dropout off. This costs zero extra GPU seconds and
    needs no second burst-node scale-up.

    Greedy (do_sample=False) so a gate result is reproducible: a sampled
    decode would make the register score vary run to run and turn a
    threshold into a coin flip.
    """
    import torch

    limit = 4 if cpu_safe else len(held_out)
    samples: List[Dict[str, Any]] = []
    stop_ids = _chat_stop_token_ids(tokenizer)
    model.eval()
    with torch.no_grad():
        for row in held_out[:limit]:
            messages = row.get("messages") or []
            if len(messages) < 2:
                continue
            prompt = tokenizer.apply_chat_template(
                messages[:-1], tokenize=False, add_generation_prompt=True
            )
            enc = tokenizer(prompt, return_tensors="pt").to(model.device)
            out = model.generate(
                **enc,
                max_new_tokens=32 if cpu_safe else 256,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                **({"eos_token_id": stop_ids} if stop_ids else {}),
            )
            decoded = tokenizer.decode(out[0][enc["input_ids"].shape[-1]:], skip_special_tokens=True)
            samples.append({
                "prompt": messages[-2].get("content", ""),
                "reference": messages[-1].get("content", ""),
                # raw kept alongside: when a register score looks wrong,
                # the decode is the first thing worth reading.
                "raw": decoded,
                "completion": _extract_answer(decoded),
            })
    logger.info("generated %d held-out completions for register scoring", len(samples))
    return samples


def stage_train_lora(config: MlopsConfig, store: ArtifactStore) -> None:
    import tempfile

    manifest = _load_dataset_manifest(config, store)
    examples_raw = store.get_bytes(f"{_run_prefix(config.dataset_prefix, config)}/examples.jsonl")
    if examples_raw is None:
        raise SystemExit(f"no examples.jsonl for {config.agent}/{config.run_id} - run prepare-dataset first")
    examples = [json.loads(line) for line in examples_raw.decode("utf-8").splitlines() if line.strip()]

    # ADR-0526 decision 8: the held-out split prepare-dataset carried
    # forward. Absent on a grounding-domain run, which is why this is a
    # soft read rather than a hard requirement.
    held_out: List[Dict[str, Any]] = []
    held_out_raw = store.get_bytes(f"{_run_prefix(config.dataset_prefix, config)}/test.jsonl")
    if held_out_raw:
        held_out = [json.loads(l) for l in held_out_raw.decode("utf-8").splitlines() if l.strip()]

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        # Resolved inside the TemporaryDirectory so an s3://-staged base
        # model's ~19GB working copy is reclaimed with the run.
        base_model_ref = _resolve_base_model(config, store, output_dir)
        train_stats = _run_lora_training(
            config, examples, output_dir, base_model_ref=base_model_ref, held_out=held_out,
        )
        adapter_prefix = f"{_run_prefix(config.model_prefix, config)}/adapter"
        uploaded = store.put_dir(adapter_prefix, output_dir / "adapter")

    # Written under the EVAL prefix, not the model one: this is gate input,
    # and evaluate is what reads it.
    register_samples = train_stats.pop("register_samples", None)
    if register_samples:
        store.put_text(
            f"{_run_prefix(config.eval_prefix, config)}/register_samples.jsonl",
            "\n".join(json.dumps(r, ensure_ascii=False) for r in register_samples),
        )

    tool_samples = train_stats.pop("tool_samples", None)
    if tool_samples:
        store.put_text(
            f"{_run_prefix(config.eval_prefix, config)}/tool_samples.jsonl",
            "\n".join(json.dumps(r, ensure_ascii=False) for r in tool_samples),
        )

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
# merge-export
# --------------------------------------------------------------------------


def stage_merge_export(config: MlopsConfig, store: ArtifactStore) -> None:
    """ADR-0526 decision 1: merges the adapter into a standalone bf16
    checkpoint and publishes it where gitops/charts/models reads models
    from.

    This is the stage that makes decision 4 possible: a merged checkpoint
    is an ordinary model, servable as its own LLMInferenceService with its
    own routable id, which is what vLLM's --lora-modules cannot give.
    Training stays adapter-scale - only the serving artifact is full size.

    Still no promotion: ADR-0302 point 7 is untouched. This writes weights
    to S3; making them serve requires a human-reviewed PR against
    gitops/charts/models/values.yaml, which nothing here touches.
    """
    import shutil
    import tempfile

    if not config.merged_model_s3uri:
        raise SystemExit("merge-export requires MLOPS_MERGED_MODEL_S3URI")
    train_manifest = store.get_json(f"{_run_prefix(config.model_prefix, config)}/train_manifest.json")
    if train_manifest is None:
        raise SystemExit(f"no train_manifest.json for {config.agent}/{config.run_id} - run train-lora first")

    dest_bucket, dest_prefix = _split_s3_uri(config.merged_model_s3uri)

    # The destination is a prefix a running KServe storage-initializer
    # reads. On the first run it is empty and no LLMInferenceService
    # points at it yet; on a re-run it holds the live variant's weights,
    # and replacing them here would swap a serving model's checkpoint
    # without the review ADR-0302 point 7 requires. Refuse by default.
    existing = store.list_keys(
        dest_prefix + "/", bucket=dest_bucket,
        region=config.models_s3_region, endpoint=config.models_s3_endpoint,
    )
    if existing and not config.merged_overwrite:
        raise SystemExit(
            f"{config.merged_model_s3uri}/ already holds {len(existing)} objects. "
            f"A served model may be reading them. Set MLOPS_MERGED_OVERWRITE=true only "
            f"if replacing those weights in place is intended."
        )

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        from peft import PeftModel
        from transformers import AutoTokenizer

        base_ref = _resolve_base_model(config, store, workdir)
        adapter_dir = workdir / "adapter"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        count = store.download_prefix(store.bucket, train_manifest["adapter_s3_prefix"], adapter_dir)
        if count == 0:
            raise SystemExit(f"no adapter files under {train_manifest['adapter_s3_prefix']}")

        model_class = _resolve_model_class(base_ref)
        kwargs: Dict[str, Any] = {}
        if not config.cpu_safe:
            import torch

            kwargs["torch_dtype"] = torch.bfloat16
        base = model_class.from_pretrained(base_ref, **kwargs)
        merged = PeftModel.from_pretrained(base, str(adapter_dir)).merge_and_unload()

        out_dir = workdir / "merged"
        merged.save_pretrained(str(out_dir), safe_serialization=True)
        AutoTokenizer.from_pretrained(str(adapter_dir)).save_pretrained(str(out_dir))

        # save_pretrained emits config + weights + tokenizer and nothing
        # else. The staged checkpoint also carries preprocessor_config.json,
        # video_preprocessor_config.json and chat_template.jinja, which vLLM
        # needs - copy forward anything the base had that the merge did not
        # produce, rather than enumerating a list that will drift.
        carried = []
        for src in sorted(Path(base_ref).iterdir()) if Path(base_ref).is_dir() else []:
            if src.is_file() and not (out_dir / src.name).exists() and not src.name.startswith("model"):
                shutil.copy2(src, out_dir / src.name)
                carried.append(src.name)
        if carried:
            logger.info("carried forward from the base checkpoint: %s", ", ".join(carried))

        files = [
            {"key": f.relative_to(out_dir).as_posix(), "size": f.stat().st_size}
            for f in sorted(out_dir.rglob("*")) if f.is_file()
        ]
        uploaded = store.put_dir(
            dest_prefix, out_dir, bucket=dest_bucket,
            region=config.models_s3_region, endpoint=config.models_s3_endpoint,
        )

    manifest = {
        "agent": config.agent,
        "run_id": config.run_id,
        "base_model": config.base_model,
        "adapter_s3_prefix": train_manifest["adapter_s3_prefix"],
        "merged_model_uri": config.merged_model_s3uri,
        "merged_bucket": dest_bucket,
        "merged_prefix": dest_prefix,
        "dtype": "float32" if config.cpu_safe else "bfloat16",
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(f["size"] for f in files),
        "uploaded_count": len(uploaded),
        "classification": train_manifest["classification"],
        "merged_at": datetime.now(timezone.utc).isoformat(),
    }
    store.put_json(f"{_run_prefix(config.model_prefix, config)}/merge_manifest.json", manifest)
    logger.info(
        "merge-export: %d files (%.1f GB) -> %s",
        len(files), manifest["total_bytes"] / 1e9, config.merged_model_s3uri,
    )


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------


def _score_register_conformance(config: MlopsConfig, store: ArtifactStore) -> Optional[Dict[str, Any]]:
    """Scores train-lora's held-out completions (ADR-0526 decision 8).

    Returns None when no samples exist - a grounding-domain run produces
    none, and that must stay a no-op rather than an automatic failure.
    Thresholds come from the agent's own gate_config.yaml, the same file
    scenario_threshold lives in (ADR-0107: thresholds are data).
    """
    raw = store.get_bytes(f"{_run_prefix(config.eval_prefix, config)}/register_samples.jsonl")
    if not raw:
        if config.style_corpus_s3uri:
            # A style run that produced no samples is a real failure: it
            # means train-lora's generation step silently did nothing, and
            # promoting on the acceptance half alone would skip decision 8.
            raise SystemExit(
                f"no register_samples.jsonl for {config.agent}/{config.run_id} but this is a "
                f"style-corpus run - ADR-0526 decision 8 requires both halves of the gate"
            )
        return None

    samples = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    sys.path.insert(0, config.evaluations_dir)
    import register_conformance  # noqa: E402
    from quality_gate import load_gate_config  # noqa: E402

    thresholds = register_conformance.thresholds_from_gate_config(load_gate_config(config.agent))
    return register_conformance.score_corpus(
        [s.get("completion", "") for s in samples], **thresholds
    )


def _install_internal_ca() -> None:
    """Trusts the platform's internal root CA for the acceptance gate.

    Every Route the gate dials (Keycloak, the agent frontends) chains to
    an internal root absent from any stock trust store, so without this
    the scenarios fail CERTIFICATE_VERIFY_FAILED - which the ADR-0028
    rate then counts as the agent misbehaving. Same mechanism
    ansible/roles/agents/tasks/run_acceptance_gate.yml uses for the
    standalone gate Job: append the CA to certifi's bundle (httpx and
    requests both verify against certifi) and point the stdlib at the
    same combined file.

    Writes to a fresh temp file rather than certifi's own bundle: the
    image's site-packages are not writable by the pod's random UID, and
    appending in place would also double the CA on a retry.

    A missing CA is not fatal here - it is left to the gate to fail
    loudly and legibly on its own HTTPS calls rather than pre-empting it
    with a less informative error.
    """
    pem = os.environ.get("ZUNO_INTERNAL_CA_PEM", "").strip()
    if not pem:
        logger.warning(
            "no ZUNO_INTERNAL_CA_PEM in the environment - every HTTPS scenario "
            "against a platform Route will fail certificate verification"
        )
        return
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi ships with requests
        logger.warning("certifi is not installed; cannot extend the trust store")
        return

    bundle = Path("/tmp/zuno-ca-bundle.pem")
    bundle.write_text(Path(certifi.where()).read_text() + "\n" + pem + "\n")
    # requests reads REQUESTS_CA_BUNDLE, httpx reads SSL_CERT_FILE via
    # ssl.create_default_context, and the subprocess the gate runs in
    # inherits both through os.environ.
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ[var] = str(bundle)
    logger.info("internal root CA appended to the trust store at %s", bundle)


def _score_tool_calling_conformance(config: MlopsConfig, store: ArtifactStore) -> Optional[Dict[str, Any]]:
    """Scores train-lora's tool-probe responses (WP-087 phase 1/2).

    Mirrors _score_register_conformance, including its asymmetry: None is a
    legitimate no-op when the agent has no probe set at all, but a run that
    HAS one and produced no samples is a hard failure - it means the
    generation step silently did nothing, and passing on the other halves
    would reintroduce exactly the blind spot this half exists to close.
    """
    if _load_tool_probes(config) is None:
        return None

    raw = store.get_bytes(f"{_run_prefix(config.eval_prefix, config)}/tool_samples.jsonl")
    if not raw:
        raise SystemExit(
            f"no tool_samples.jsonl for {config.agent}/{config.run_id} but "
            f"evaluations/{config.agent}/tool_probes.yaml exists - the tool-calling "
            f"half cannot be skipped once an agent declares a probe set"
        )
    samples = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]

    sys.path.insert(0, config.evaluations_dir)
    import tool_calling_conformance  # noqa: E402
    from quality_gate import load_gate_config  # noqa: E402

    thresholds = tool_calling_conformance.thresholds_from_gate_config(load_gate_config(config.agent))
    return tool_calling_conformance.score_corpus(samples, **thresholds)


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

    _install_internal_ca()

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

    # ADR-0526 decision 8: the register half, AND-ed with the acceptance
    # result above. Computed independently rather than as extra scenarios,
    # because scenarios land in the ADR-0028 DENOMINATOR - 3 register
    # scenarios added to comage's 20 and all 3 failing still scores
    # 20/23 = 87% >= 75% and reports PASS. That would not implement
    # decision 8 at all.
    register = _score_register_conformance(config, store)
    if register is not None:
        result["register_conformance"] = register
        if result.get("overall") == "PASS" and not register.get("passed"):
            result["overall"] = "FAIL"
            result["register_failure"] = register.get("failures")

    # WP-087 phase 2: the third half. Same AND, same reason - the register
    # and acceptance halves both passed on four consecutive runs while the
    # variant stopped calling tools entirely, because neither of them looks
    # at tool calls.
    tool_calling = _score_tool_calling_conformance(config, store)
    if tool_calling is not None:
        result["tool_calling_conformance"] = tool_calling
        if result.get("overall") == "PASS" and not tool_calling.get("passed"):
            result["overall"] = "FAIL"
            result["tool_calling_failure"] = tool_calling.get("failures")

    store.put_json(f"{_run_prefix(config.eval_prefix, config)}/gate_result.json", result)
    # A stage that fails must say what failed in its own log. Reading the
    # first end-to-end run meant fetching gate_result.json out of S3 by
    # hand to learn anything past three booleans.
    if result.get("overall") != "PASS":
        summary = result.get("summary") or {}
        for layer in ("scenarios", "security_checks", "gate_checks"):
            for item in (summary.get(layer) or {}).get("failed", []):
                logger.warning(
                    "evaluate: %s FAILED %s: %s",
                    layer,
                    item.get("name") or item.get("id"),
                    (item.get("detail") or "").strip() or "(no detail)",
                )
        for failure in (register or {}).get("failures", []):
            logger.warning("evaluate: register FAILED %s", failure)
        for failure in (tool_calling or {}).get("failures", []):
            logger.warning("evaluate: tool-calling FAILED %s", failure)
    logger.info(
        "evaluate: %s/%s acceptance=%s register=%s tools=%s -> %s",
        config.agent, config.run_id,
        result.get("scenario_rate", "n/a"),
        "n/a" if register is None else ("PASS" if register.get("passed") else "FAIL"),
        "n/a" if tool_calling is None else ("PASS" if tool_calling.get("passed") else "FAIL"),
        result.get("overall"),
    )
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
    # WP-087: WP-34's default named modelregistry-sample:8080 over plain
    # HTTP. No such Service exists - not in this namespace, not anywhere -
    # which is one reason push-registry has never run successfully.
    #
    # Every part is a VALUE, not a literal, and deliberately so: nothing in
    # this repository creates or names a ModelRegistry instance (the
    # openshift-ai chart only sets registriesNamespace), so the service
    # name, port and scheme are operator observations, not facts this repo
    # owns. UNVERIFIED against a live cluster - an operator corrects a Helm
    # value here, never code.
    return (
        f"{config.model_registry_scheme}://{config.model_registry_service}"
        f".{config.model_registry_namespace}.svc.cluster.local:{config.model_registry_port}"
    )


def _registry_session(config: MlopsConfig) -> "requests.Session":
    """A requests Session carrying the Model Registry's auth and TLS trust.

    WP-34 issued three bare requests.post calls: no Authorization header
    and no CA bundle, which cannot work against an HTTPS, authenticated
    registry. The token is read fresh from disk at call time (a projected
    ServiceAccount token is rotated in place, so caching its contents at
    import would eventually send an expired one), and verification uses
    the cluster's service-CA bundle - the same pattern app/providers.py
    and app/maas_adapter.py already use for in-cluster TLS.
    """
    session = requests.Session()
    token = os.environ.get("MODEL_REGISTRY_TOKEN")
    if not token and config.model_registry_token_path:
        token_file = Path(config.model_registry_token_path)
        if token_file.is_file():
            token = token_file.read_text(encoding="utf-8").strip()
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    else:
        logger.warning(
            "no Model Registry token available (MODEL_REGISTRY_TOKEN unset, %s absent) - "
            "the registry call will be unauthenticated",
            config.model_registry_token_path,
        )
    ca = config.model_registry_ca_bundle
    if ca and Path(ca).is_file():
        session.verify = ca
    elif config.model_registry_scheme == "https":
        logger.warning("CA bundle %s not found; falling back to the system trust store", ca)
    return session


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
    model_name = config.registered_model_name or f"{config.agent}-lora"
    version_name = config.run_id
    session = _registry_session(config)

    # ADR-0526 acceptance: "a model version whose artifact URI points at
    # the MERGED checkpoint in S3". Falls back to the adapter prefix when
    # no merge ran, so a grounding-domain run still registers something
    # meaningful rather than failing on a missing manifest.
    merge_manifest = store.get_json(f"{_run_prefix(config.model_prefix, config)}/merge_manifest.json")
    if merge_manifest and merge_manifest.get("merged_model_uri"):
        artifact_uri = merge_manifest["merged_model_uri"]
    else:
        artifact_uri = f"s3://{config.s3_bucket}/{train_manifest['adapter_s3_prefix']}"

    registered_model = session.post(
        f"{base_url}/api/model_registry/v1alpha3/registered_models",
        json={"name": model_name, "description": f"LoRA adapter for {config.agent} (ADR-0301/WP-34)"},
        timeout=30,
    )
    registered_model.raise_for_status()
    registered_model_id = registered_model.json()["id"]

    model_version = session.post(
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

    model_artifact = session.post(
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
    "merge-export": stage_merge_export,
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
