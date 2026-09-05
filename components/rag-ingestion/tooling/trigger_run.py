#!/usr/bin/env python3
"""Trigger one on-demand KFP run of a rag-ingestion knowledge.tech pipeline.

WP-129. Reads KFP_HOST/KFP_TOKEN from the environment, never argv, so the
bearer token never shows up in a process list (`ps aux`).

Resolves the per-family Pipeline (display name "RAG corpus ingestion
(tech-<family>)"), its latest PipelineVersion, and the "Default" Experiment
over the raw v2beta1 REST API - the same API surface
ansible/roles/rag_ingestion/tasks/recurring_run.yml already uses for the
scheduled runs, just POSTing to /apis/v2beta1/runs instead of
/apis/v2beta1/recurringruns for a one-off. Confirmed live against this
DSPA (2026-09-04): pipeline display names, the "Default" experiment id, and
the run body shape (experiment_id + pipeline_version_reference, no
service_account needed - the DSPA defaults it) were all read back from a
real successful run (tech-argocd, 2026-09-03) before this script was
written, mirroring the ad hoc sequence used to trigger argocd/helm.

Usage:

    KFP_HOST=https://ds-pipeline-rag-dspa-zuno-ai-build.apps... \
    KFP_TOKEN=$(oc whoami -t) \
    python3 trigger_run.py --family redhat-odf
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import ssl
import sys
import urllib.request

_EXPERIMENT_DISPLAY_NAME = "Default"


def _get(host: str, token: str, path: str) -> dict:
    req = urllib.request.Request(
        f"{host}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.load(resp)


def _post(host: str, token: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{host}{path}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.load(resp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--family", help="a knowledge.tech source, e.g. redhat-odf")
    group.add_argument(
        "--domain",
        help="a non-tech domain whose pipeline display name has no "
        "'tech-' prefix (values.yaml's top-level `domains:`, e.g. sxa-legacy)",
    )
    parser.add_argument("--tag", default="wp129-manual")
    args = parser.parse_args()

    host = os.environ["KFP_HOST"]
    token = os.environ["KFP_TOKEN"]

    display_name = (
        f"RAG corpus ingestion (tech-{args.family})"
        if args.family
        else f"RAG corpus ingestion ({args.domain})"
    )
    pipelines = _get(host, token, "/apis/v2beta1/pipelines?page_size=100").get(
        "pipelines", []
    )
    matches = [p for p in pipelines if p["display_name"] == display_name]
    if not matches:
        print(f"No pipeline named {display_name!r} found.", file=sys.stderr)
        return 1
    pipeline_id = matches[0]["pipeline_id"]

    versions = _get(
        host,
        token,
        f"/apis/v2beta1/pipelines/{pipeline_id}/versions?sort_by=created_at%20desc&page_size=1",
    ).get("pipeline_versions", [])
    if not versions:
        print(f"Pipeline {display_name!r} has no versions.", file=sys.stderr)
        return 1
    version_id = versions[0]["pipeline_version_id"]

    experiments = _get(host, token, "/apis/v2beta1/experiments?page_size=20").get(
        "experiments", []
    )
    default_experiments = [
        e for e in experiments if e["display_name"] == _EXPERIMENT_DISPLAY_NAME
    ]
    if not default_experiments:
        print(f"No {_EXPERIMENT_DISPLAY_NAME!r} KFP experiment found.", file=sys.stderr)
        return 1
    experiment_id = default_experiments[0]["experiment_id"]

    run_name_prefix = f"tech-{args.family}" if args.family else args.domain
    run_name = f"{run_name_prefix}-{args.tag}-{datetime.datetime.now():%Y%m%d%H%M%S}"
    run = _post(
        host,
        token,
        "/apis/v2beta1/runs",
        {
            "display_name": run_name,
            "experiment_id": experiment_id,
            "pipeline_version_reference": {
                "pipeline_id": pipeline_id,
                "pipeline_version_id": version_id,
            },
        },
    )
    print(f"run_id={run.get('run_id')} display_name={run_name}")
    print(f"{host}/#/runs/details/{run.get('run_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
