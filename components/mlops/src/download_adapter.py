#!/usr/bin/env python3
"""Init-container entrypoint: downloads a registered LoRA adapter from S3
onto a serving pod's local filesystem (ADR-0301 point 2, WP-133).

Deliberately standalone - does NOT import mlops.py/load_config(). That
config loader assumes a KFP stage's full env contract (MLOPS_AGENT,
MLOPS_RUN_ID, Postgres credentials, Model Registry token, evaluation
paths...). A serving pod carries none of that, and forcing it to would
couple LLMInferenceService's env to the whole mlops pipeline's config
surface for no reason - this only needs an S3 credential (the same one
gitops/charts/models' own s3-serving-credentials-*.yaml already mounts for
the base model) plus the adapter's own source/destination.

Run once per gitops/charts/models `loraAdapters` entry, as one
initContainer per adapter (see templates/llminferenceservice-qwen35.yaml).
Refuses to leave an empty destination behind: vLLM's --lora-modules would
otherwise start against a directory with no adapter in it and fail with a
much less legible error inside the main container.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config as BotoClientConfig


def _env(name: str, *, required: bool = False) -> str:
    value = os.environ.get(name, "").strip()
    if required and not value:
        raise SystemExit(f"{name} is required")
    return value


def _split_s3_uri(uri: str) -> tuple:
    """s3://bucket/prefix -> (bucket, prefix). Mirrors mlops.py's own
    _split_s3_uri - kept as a private copy rather than importing mlops.py,
    per this module's own standalone-on-purpose design (see docstring)."""
    if not uri.startswith("s3://"):
        raise SystemExit(f"not an s3:// URI: {uri}")
    bucket, _, prefix = uri[len("s3://") :].partition("/")
    if not bucket or not prefix:
        raise SystemExit(f"malformed s3:// URI (need bucket and key/prefix): {uri}")
    return bucket, prefix.rstrip("/")


def _s3_client():
    # WP-133 (live, 2026-09-04): gitops/charts/models' modelsS3.endpoint is
    # a bare hostname (s3.eu-west-2.amazonaws.com) - the convention its own
    # serving.kserve.io/s3-endpoint annotation tolerates, but boto3's
    # endpoint_url requires a full scheme-prefixed URL and raises
    # ValueError("Invalid endpoint: ...") on a bare host. Confirmed live:
    # the initContainer crash-looped on exactly this before the fix.
    endpoint = _env("S3_ENDPOINT") or None
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    region = _env("S3_REGION") or None
    path_style = _env("S3_PATH_STYLE").lower() == "true"
    client_kwargs = {
        "region_name": region,
        "aws_access_key_id": _env("AWS_ACCESS_KEY_ID", required=True),
        "aws_secret_access_key": _env("AWS_SECRET_ACCESS_KEY", required=True),
        "config": BotoClientConfig(s3={"addressing_style": "path" if path_style else "auto"}),
    }
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **client_kwargs)


def download_adapter(client, source_s3uri: str, dest_path: str) -> int:
    bucket, prefix = _split_s3_uri(source_s3uri)
    key_prefix = prefix.rstrip("/") + "/"
    dest = Path(dest_path)
    dest.mkdir(parents=True, exist_ok=True)

    paginator = client.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
        for obj in page.get("Contents", []):
            rel = obj["Key"][len(key_prefix) :]
            if not rel:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, obj["Key"], str(target))
            count += 1

    if count == 0:
        raise SystemExit(
            f"no adapter files found under {source_s3uri} - refusing to leave "
            f"{dest_path} empty for vLLM's --lora-modules to fail on later"
        )
    return count


def main() -> int:
    source = _env("ADAPTER_SOURCE_S3URI", required=True)
    dest = _env("ADAPTER_DEST_PATH", required=True)
    count = download_adapter(_s3_client(), source, dest)
    print(f"download-adapter: {count} file(s) {source} -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
