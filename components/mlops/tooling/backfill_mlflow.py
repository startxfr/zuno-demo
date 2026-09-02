#!/usr/bin/env python3
"""One-off: backfill an already-completed MLOps run into MLflow (WP-116).

ADR-0538 decision 2 says MLflow mirrors the S3 manifests rather than
replacing them - which means a run that finished BEFORE the tracking
integration existed can be reconstructed from those manifests exactly as
well as a live one. That is what this does for
`wesh-20260829-145123` (ADR-0526's one green run), so the Experiments page
shows real history immediately instead of waiting ~2h of burst-node GPU for
a fresh run.

Deliberately NOT wired into the pipeline and NOT copied into the image: it
is a one-off, run in-cluster from a ConfigMap mount so it can reach both S3
and the tracking server. It reuses src/mlflow_tracking.py rather than
reimplementing the protocol, so the backfilled run is shaped exactly like a
live one.

Idempotent: a run already tagged with this zuno_run_id is left alone, so a
re-run after a partial failure cannot create duplicates.

Every backfilled run carries `zuno_backfilled=true`. That tag is the honest
part - these rows were reconstructed after the fact from manifests, not
observed live, and nobody reading the Experiments page later should have to
guess which is which.

Usage (in-cluster, with the mlops image's env):

    python3 backfill_mlflow.py --agent comage --run-id wesh-20260829-145123
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, "/opt/app-root/src")

import boto3  # noqa: E402
import mlflow_tracking as mt  # noqa: E402


def _s3_client():
    endpoint = os.environ.get("S3_ENDPOINT") or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("S3_REGION") or None,
    )


def _get_json(client, bucket: str, key: str) -> Optional[Dict[str, Any]]:
    try:
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)
    except Exception as exc:  # noqa: BLE001
        print(f"  (no {key}: {exc})")
        return None


def _epoch_ms(iso: Optional[str]) -> Optional[int]:
    """The manifests carry ISO-8601 created_at; MLflow wants epoch ms. A
    missing/unparseable timestamp falls back to 'now' rather than failing -
    a run at the wrong time is still better than no run."""
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backfill one MLOps run into MLflow")
    p.add_argument("--agent", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--bucket", default=os.environ.get("S3_BUCKET", "zuno-corpus"))
    p.add_argument("--model-prefix", default=os.environ.get("S3_MODEL_PREFIX", "mlops/models"))
    p.add_argument("--eval-prefix", default=os.environ.get("S3_EVAL_PREFIX", "mlops/evaluations"))
    args = p.parse_args(argv)

    if not mt.tracking_uri():
        print("ERROR: MLFLOW_TRACKING_URI is unset - nothing to back fill into")
        return 2

    client = _s3_client()
    base = f"{args.agent}/{args.run_id}"
    print(f"reading manifests for {base} from s3://{args.bucket}")
    train_manifest = _get_json(client, args.bucket, f"{args.model_prefix}/{base}/train_manifest.json")
    gate_result = _get_json(client, args.bucket, f"{args.eval_prefix}/{base}/gate_result.json")
    if train_manifest is None and gate_result is None:
        print("ERROR: neither manifest exists - wrong run id, bucket or prefixes?")
        return 1

    experiment = f"mlops-{args.agent}"
    experiment_id = mt._experiment_id(experiment)
    if not experiment_id:
        print(f"ERROR: could not resolve or create experiment {experiment}")
        return 1
    if mt._find_run(experiment_id, args.run_id):
        print(f"run {args.run_id} already present in {experiment} - nothing to do")
        return 0

    mlflow_run_id = mt.log_training(
        agent=args.agent,
        run_id=args.run_id,
        manifest=train_manifest or {},
        start_time_ms=_epoch_ms((train_manifest or {}).get("created_at")),
        # end_run is left False here: log_gate below closes the run with the
        # status the gate actually produced, which is more informative than
        # a blanket FINISHED.
    )
    if not mlflow_run_id:
        print("ERROR: failed to create the MLflow run")
        return 1
    print(f"created MLflow run {mlflow_run_id} from train_manifest")

    mt._call("POST", "runs/set-tag",
             json={"run_id": mlflow_run_id, "key": "zuno_backfilled", "value": "true"})

    if gate_result:
        mt.log_gate(agent=args.agent, run_id=args.run_id, result=gate_result)
        print(f"logged gate result: {gate_result.get('overall')}")
    else:
        mt._call("POST", "runs/update",
                 json={"run_id": mlflow_run_id, "status": "FINISHED"})

    print(f"backfill complete: experiment={experiment} run={args.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
