"""Copy the pinned world-model weights from S3 into the pod's model cache (ADR-0604 WP-230/231).

Runs in the storage-initializer image (it ships boto3) as an init container:

    python3 fetch_models.py /models

Env: WORLD_MODEL_S3_BUCKET, WORLD_MODEL_S3_PREFIX (default models/world-model),
AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and WORLD_MODEL_REVISIONS,
a JSON map {"<org>/<repo>": "<revision>"} copied from models.lock.yaml. Only
those revisions are copied; the S3 key <prefix>/<org>/<repo>/<revision>/<path>
lands at <dest>/<org>/<repo>/<path>. A file already present with the right size
is kept, so a pod restart on the same node does not copy 20 GB again.
"""
from __future__ import annotations

import json
import os
import sys
import time


def main(dest: str) -> int:
    import boto3
    from botocore.config import Config

    bucket = os.environ["WORLD_MODEL_S3_BUCKET"]
    prefix = os.environ.get("WORLD_MODEL_S3_PREFIX", "models/world-model").strip("/")
    revisions = json.loads(os.environ["WORLD_MODEL_REVISIONS"])
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION"),
                      config=Config(signature_version="s3v4", retries={"max_attempts": 5}))
    total = copied = 0
    for repo, revision in revisions.items():
        root = f"{prefix}/{repo}/{revision}/"
        found = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=root):
            for obj in page.get("Contents", []):
                rel = obj["Key"][len(root):]
                if not rel or rel.startswith("/") or ".." in rel.split("/"):
                    continue
                target = os.path.join(dest, repo, rel)
                found += 1
                total += obj["Size"]
                if os.path.exists(target) and os.path.getsize(target) == obj["Size"]:
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                started = time.time()
                s3.download_file(bucket, obj["Key"], target + ".part")
                if os.path.getsize(target + ".part") != obj["Size"]:
                    raise RuntimeError(f"size mismatch for {obj['Key']}")
                os.replace(target + ".part", target)
                copied += obj["Size"]
                print(f"{repo}/{rel}: {obj['Size']} bytes in {time.time() - started:.1f}s", flush=True)
        if not found:
            raise RuntimeError(f"nothing under s3://{bucket}/{root}: is the revision mirrored (WP-230)?")
    print(f"model cache ready: {total} bytes, {copied} copied now", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/models"))
