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

Env contract:
    ADAPTER_SOURCE_S3URI  - s3://bucket/prefix, from the adapter's own
                            registration.json (push-registry's
                            artifact_uri) - never an ad hoc location
                            (ADR-0301 point 3).
    ADAPTER_DEST_PATH     - local filesystem path, matches this entry's
                            values.yaml `path` (what --lora-modules
                            reads from).
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY - mounted from the same
                            Secret the base model's storage-initializer
                            already uses.
    S3_PATH_STYLE         - optional, mirrors modelsS3.pathStyle if this
                            bucket ever needs path-style addressing.

No region/endpoint input: the adapter's bucket is discovered and dialed
directly (_bucket_region/_s3_client below) rather than assumed to share
gitops/charts/models' modelsS3 region - it does not (see _bucket_region's
own docstring for the live PermanentRedirect this replaced).
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


def _s3_client(*, region: str, path_style: bool):
    # No explicit endpoint_url: boto3 derives the correct regional endpoint
    # from region_name alone, the same pattern mlops.py's own ArtifactStore
    # uses for its cross-region client (ArtifactStore._client_for) - an
    # explicit override is exactly what caused this script's earlier
    # PermanentRedirect (a hardcoded eu-west-2 endpoint for a us-east-1
    # bucket).
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=_env("AWS_ACCESS_KEY_ID", required=True),
        aws_secret_access_key=_env("AWS_SECRET_ACCESS_KEY", required=True),
        config=BotoClientConfig(s3={"addressing_style": "path" if path_style else "auto"}),
    )


def _bucket_region(bucket: str, *, path_style: bool) -> str:
    """GetBucketLocation answers from ANY region's endpoint, so a us-east-1
    client can always ask it - the standard boto3 bootstrap pattern.

    WP-133 (live, 2026-09-04): the adapter's own artifact bucket
    (components/mlops's s3.bucket, us-east-1 - see gitops/charts/mlops/
    values.yaml) is NOT gitops/charts/models' modelsS3.bucket (eu-west-2).
    A client pinned to the wrong region gets PermanentRedirect on every
    call, confirmed live: hardcoding modelsS3.region/endpoint here was the
    bug this function replaces. An empty LocationConstraint means
    us-east-1 (S3's own historical quirk - the API omits it for that one
    region rather than naming it).
    """
    bootstrap = _s3_client(region="us-east-1", path_style=path_style)
    return bootstrap.get_bucket_location(Bucket=bucket).get("LocationConstraint") or "us-east-1"


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
    path_style = _env("S3_PATH_STYLE").lower() == "true"
    bucket, _ = _split_s3_uri(source)
    region = _bucket_region(bucket, path_style=path_style)
    client = _s3_client(region=region, path_style=path_style)
    count = download_adapter(client, source, dest)
    print(f"download-adapter: {count} file(s) {source} -> {dest} (region {region})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
